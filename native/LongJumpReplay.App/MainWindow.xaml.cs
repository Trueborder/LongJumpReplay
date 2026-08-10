using System.ComponentModel;
using System.IO;
using System.Windows;
using System.Windows.Input;
using System.Windows.Media;
using System.Windows.Media.Imaging;
using LongJumpReplay.Core;
using LongJumpReplay.Infrastructure;
using LongJumpReplay.Video.Windows;

namespace LongJumpReplay.App;

public partial class MainWindow : Window
{
    private sealed record SourceChoice(string Name, string? DeviceId);

    private readonly ReplayCoordinator _replay = new(TimeSpan.FromSeconds(5), 180);
    private IVideoSource _source = new SyntheticVideoSource();
    private WriteableBitmap? _bitmap;
    private int _renderPending;
    private bool _paused;
    private bool _closing;
    private readonly bool _isCzech;

    public MainWindow()
    {
        InitializeComponent();
        _isCzech = LoadLanguage() == "cs";
        ApplyLanguage();
        SourceText.Text = T("Synthetic camera · 480×270 · 30 fps", "Syntetická kamera · 480×270 · 30 fps");
        _source.FrameReady += Source_FrameReady;
        Loaded += Window_Loaded;
        UpdateStatus();
    }

    private async void Window_Loaded(object sender, RoutedEventArgs e)
    {
        await _source.StartAsync();
        var choices = new List<SourceChoice> { new(T("Synthetic camera", "Syntetická kamera"), null) };
        try
        {
            var devices = await MediaFoundationCameraSource.ListDevicesAsync();
            choices.AddRange(devices.Select(device => new SourceChoice(device.Name, device.Id)));
        }
        catch (Exception error)
        {
            StatusText.Text = T($"Camera enumeration failed: {error.Message}", $"Výpis kamer selhal: {error.Message}");
        }
        SourceSelector.ItemsSource = choices;
        SourceSelector.SelectedIndex = 0;
    }

    private static string LoadLanguage()
    {
        try
        {
            var path = Path.Combine(Environment.CurrentDirectory, "config.json");
            return File.Exists(path) ? CompatibleConfig.Load(path).Language : "en";
        }
        catch { return "en"; }
    }

    private string T(string english, string czech) => _isCzech ? czech : english;

    private void ApplyLanguage()
    {
        Title = T("Long Jump Replay · Native migration preview", "Long Jump Replay · Náhled nativní migrace");
        EarlierText.Text = T("Earlier", "Dříve");
        LatestText.Text = T("Latest", "Nejnovější");
        PreviousFrameButton.Content = T("◀ Frame", "◀ Snímek");
        NextFrameButton.Content = T("Frame ▶", "Snímek ▶");
        PauseButton.Content = T("Pause camera", "Pozastavit kameru");
        UseSourceButton.Content = T("Use source", "Použít zdroj");
    }

    private async void UseSourceButton_Click(object sender, RoutedEventArgs e)
    {
        if (SourceSelector.SelectedItem is not SourceChoice choice || _closing) return;
        UseSourceButton.IsEnabled = false;
        var previous = _source;
        previous.FrameReady -= Source_FrameReady;
        try
        {
            await previous.StopAsync(TimeSpan.FromSeconds(2));
            await previous.DisposeAsync();
        }
        catch (Exception error)
        {
            previous.FrameReady += Source_FrameReady;
            StatusText.Text = T($"Could not stop the current source: {error.Message}", $"Aktuální zdroj nelze zastavit: {error.Message}");
            UseSourceButton.IsEnabled = true;
            return;
        }
        IVideoSource? candidate = null;
        try
        {
            candidate = choice.DeviceId is null ? new SyntheticVideoSource() : new MediaFoundationCameraSource(choice.DeviceId);
            candidate.FrameReady += Source_FrameReady;
            await candidate.StartAsync();
            _source = candidate;
            SourceText.Text = _source.Description;
            _paused = false;
            PauseButton.Content = T("Pause camera", "Pozastavit kameru");
        }
        catch (Exception error)
        {
            if (candidate is not null)
            {
                candidate.FrameReady -= Source_FrameReady;
                try { await candidate.DisposeAsync(); } catch { }
            }
            StatusText.Text = T($"Source failed: {error.Message}", $"Zdroj selhal: {error.Message}");
            _source = new SyntheticVideoSource();
            _source.FrameReady += Source_FrameReady;
            await _source.StartAsync();
            SourceSelector.SelectedIndex = 0;
            SourceText.Text = T("Synthetic fallback", "Syntetický náhradní zdroj");
        }
        finally { UseSourceButton.IsEnabled = true; }
    }

    private void Source_FrameReady(object? sender, VideoFrame frame)
    {
        _replay.OnFrame(frame);
        if (_replay.Mode != PlaybackMode.Live || Interlocked.Exchange(ref _renderPending, 1) != 0) return;
        _ = Dispatcher.InvokeAsync(() =>
        {
            try { Render(_replay.DisplayedFrame()); UpdateStatus(); }
            finally { Interlocked.Exchange(ref _renderPending, 0); }
        });
    }

    private void Render(VideoFrame? frame)
    {
        if (frame is null) return;
        if (_bitmap is null || _bitmap.PixelWidth != frame.Width || _bitmap.PixelHeight != frame.Height)
        {
            _bitmap = new WriteableBitmap(frame.Width, frame.Height, 96, 96, PixelFormats.Bgra32, null);
            VideoImage.Source = _bitmap;
        }
        _bitmap.WritePixels(new Int32Rect(0, 0, frame.Width, frame.Height), frame.Bgra32, frame.Width * 4, 0);
    }

    private void ToggleFreeze()
    {
        if (_paused) return;
        if (_replay.Mode == PlaybackMode.Live)
        {
            if (_replay.Freeze()) Render(_replay.DisplayedFrame());
        }
        else _replay.ReturnLive();
        UpdateStatus();
    }

    private void UpdateStatus()
    {
        var state = _replay.Snapshot();
        ModeText.Text = _paused ? T("PAUSED", "POZASTAVENO") : state.Mode == PlaybackMode.Live ? T("LIVE", "ŽIVĚ") : "REPLAY";
        ModeText.Foreground = new SolidColorBrush((Color)ColorConverter.ConvertFromString(_paused ? "#F2B84B" : state.Mode == PlaybackMode.Live ? "#44D19D" : "#65A4FF"));
        FreezeButton.Content = state.Mode == PlaybackMode.Live ? T("Freeze", "Zmrazit") : T("Return Live", "Zpět živě");
        StatusText.Text = T(
            $"Frames buffered: {state.BufferedFrames} · Displayed: {state.DisplayedSequence?.ToString() ?? "none"}",
            $"Snímků v bufferu: {state.BufferedFrames} · Zobrazený: {state.DisplayedSequence?.ToString() ?? "žádný"}");
        Timeline.Value = state.BufferedFrames == 0 ? 0 : state.Mode == PlaybackMode.Live ? 100 : Math.Clamp((state.DisplayedSequence ?? 0) % 100, 0, 100);
    }

    private void FreezeButton_Click(object sender, RoutedEventArgs e) => ToggleFreeze();
    private void PreviousFrame_Click(object sender, RoutedEventArgs e) { Render(_replay.Step(-1)); UpdateStatus(); }
    private void NextFrame_Click(object sender, RoutedEventArgs e) { Render(_replay.Step(1)); UpdateStatus(); }

    private async void PauseButton_Click(object sender, RoutedEventArgs e)
    {
        if (_paused)
        {
            _paused = false;
            await _source.StartAsync();
            PauseButton.Content = T("Pause camera", "Pozastavit kameru");
        }
        else
        {
            _paused = true;
            _replay.ReturnLive();
            await _source.StopAsync(TimeSpan.FromSeconds(2));
            PauseButton.Content = T("Resume camera", "Obnovit kameru");
        }
        UpdateStatus();
    }

    private void Window_KeyDown(object sender, KeyEventArgs e)
    {
        if (e.Key == Key.Space) { ToggleFreeze(); e.Handled = true; }
        else if (e.Key == Key.Home) { _replay.ReturnLive(); UpdateStatus(); e.Handled = true; }
        else if (e.Key == Key.Left) { Render(_replay.Step(-1)); UpdateStatus(); e.Handled = true; }
        else if (e.Key == Key.Right) { Render(_replay.Step(1)); UpdateStatus(); e.Handled = true; }
    }

    private async void Window_Closing(object? sender, CancelEventArgs e)
    {
        if (_closing) return;
        _closing = true;
        e.Cancel = true;
        try { await _source.StopAsync(TimeSpan.FromSeconds(2)); }
        finally { Closing -= Window_Closing; Close(); }
    }
}
