using System.Diagnostics;
using LongJumpReplay.Core;
using Windows.Devices.Enumeration;
using Windows.Graphics.Imaging;
using Windows.Media.Capture;
using Windows.Media.Capture.Frames;
using Windows.Media.MediaProperties;
using Windows.Storage.Streams;

namespace LongJumpReplay.Video.Windows;

public interface IVideoSource : IAsyncDisposable
{
    string Description { get; }
    bool IsRunning { get; }
    event EventHandler<VideoFrame>? FrameReady;
    Task StartAsync(CancellationToken cancellationToken = default);
    Task StopAsync(TimeSpan timeout);
}

/// <summary>Deterministic source used to validate the native UI and lifecycle without camera hardware.</summary>
public sealed class SyntheticVideoSource(int width = 480, int height = 270, double fps = 30) : IVideoSource
{
    private readonly object _gate = new();
    private CancellationTokenSource? _stop;
    private Task? _worker;
    private long _sequence;

    public string Description => $"Synthetic camera · {width}×{height} · {fps:F0} fps";
    public bool IsRunning => _worker is { IsCompleted: false };
    public event EventHandler<VideoFrame>? FrameReady;

    public Task StartAsync(CancellationToken cancellationToken = default)
    {
        lock (_gate)
        {
            if (IsRunning) return Task.CompletedTask;
            _stop = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
            _worker = Task.Run(() => RunAsync(_stop.Token), CancellationToken.None);
        }
        return Task.CompletedTask;
    }

    private async Task RunAsync(CancellationToken cancellationToken)
    {
        var background = CreateBackground();
        var period = TimeSpan.FromSeconds(1.0 / Math.Max(1, fps));
        using var timer = new PeriodicTimer(period);
        while (await timer.WaitForNextTickAsync(cancellationToken).ConfigureAwait(false))
        {
            var sequence = Interlocked.Increment(ref _sequence) - 1;
            var pixels = (byte[])background.Clone();
            DrawRunner(pixels, sequence);
            FrameReady?.Invoke(this, new VideoFrame(sequence, Stopwatch.GetTimestamp(), width, height, pixels));
        }
    }

    private byte[] CreateBackground()
    {
        var pixels = new byte[width * height * 4];
        for (var y = 0; y < height; y++)
        for (var x = 0; x < width; x++)
        {
            var grid = x % 40 == 0 || y % 40 == 0;
            var shade = (byte)(grid ? 54 : 28);
            var offset = (y * width + x) * 4;
            pixels[offset] = shade;
            pixels[offset + 1] = shade;
            pixels[offset + 2] = shade;
            pixels[offset + 3] = 255;
        }
        var boardX = (int)(width * .68);
        FillRect(pixels, boardX - 3, 25, 6, height - 50, 240, 240, 240);
        return pixels;
    }

    private void DrawRunner(byte[] pixels, long sequence)
    {
        var phase = (sequence % 120) / 119.0;
        var x = (int)(20 + phase * (width - 40));
        var y = (int)(height * .58 + Math.Sin(phase * Math.PI * 4) * 16);
        FillRect(pixels, x - 18, y - 7, 36, 14, 20, 190, 255);
    }

    private void FillRect(byte[] pixels, int left, int top, int rectWidth, int rectHeight, byte b, byte g, byte r)
    {
        for (var y = Math.Max(0, top); y < Math.Min(height, top + rectHeight); y++)
        for (var x = Math.Max(0, left); x < Math.Min(width, left + rectWidth); x++)
        {
            var offset = (y * width + x) * 4;
            pixels[offset] = b; pixels[offset + 1] = g; pixels[offset + 2] = r; pixels[offset + 3] = 255;
        }
    }

    public async Task StopAsync(TimeSpan timeout)
    {
        Task? worker;
        lock (_gate)
        {
            _stop?.Cancel();
            worker = _worker;
        }
        if (worker is null) return;
        try { await worker.WaitAsync(timeout).ConfigureAwait(false); }
        catch (OperationCanceledException) { }
        catch (TimeoutException) { throw new TimeoutException("Video source did not stop within the bounded timeout."); }
        finally
        {
            lock (_gate) { _stop?.Dispose(); _stop = null; _worker = null; }
        }
    }

    public async ValueTask DisposeAsync() => await StopAsync(TimeSpan.FromSeconds(2)).ConfigureAwait(false);
}

public sealed record CameraDeviceInfo(string Id, string Name);

/// <summary>Windows Media Foundation/MediaCapture source kept outside WPF behind IVideoSource.</summary>
public sealed class MediaFoundationCameraSource(string deviceId, int requestedWidth = 0, int requestedHeight = 0, double requestedFps = 0) : IVideoSource
{
    private readonly SemaphoreSlim _lifecycle = new(1, 1);
    private MediaCapture? _capture;
    private MediaFrameReader? _reader;
    private long _sequence;
    private int _copyingFrame;
    private volatile bool _running;

    public string Description { get; private set; } = $"Media Foundation camera · {deviceId}";
    public bool IsRunning => _running;
    public event EventHandler<VideoFrame>? FrameReady;

    public static async Task<IReadOnlyList<CameraDeviceInfo>> ListDevicesAsync()
    {
        var devices = await DeviceInformation.FindAllAsync(DeviceClass.VideoCapture);
        return devices.Select(device => new CameraDeviceInfo(device.Id, device.Name)).ToArray();
    }

    public async Task StartAsync(CancellationToken cancellationToken = default)
    {
        await _lifecycle.WaitAsync(cancellationToken).ConfigureAwait(false);
        try
        {
            if (_running) return;
            var capture = new MediaCapture();
            try
            {
                var settings = new MediaCaptureInitializationSettings
                {
                    VideoDeviceId = deviceId,
                    StreamingCaptureMode = StreamingCaptureMode.Video,
                    MemoryPreference = MediaCaptureMemoryPreference.Cpu,
                    SharingMode = MediaCaptureSharingMode.ExclusiveControl,
                };
                await capture.InitializeAsync(settings);
                cancellationToken.ThrowIfCancellationRequested();
                var source = capture.FrameSources.Values.FirstOrDefault(value => value.Info.SourceKind == MediaFrameSourceKind.Color)
                    ?? throw new InvalidOperationException("The selected camera does not expose a color frame source.");
                var requested = source.SupportedFormats
                    .Where(format => format.VideoFormat.Width > 0 && format.VideoFormat.Height > 0)
                    .OrderBy(format =>
                    {
                        var fps = format.FrameRate.Denominator == 0 ? 0 : (double)format.FrameRate.Numerator / format.FrameRate.Denominator;
                        var sizePenalty = Math.Abs((long)format.VideoFormat.Width - requestedWidth) + Math.Abs((long)format.VideoFormat.Height - requestedHeight);
                        var fpsPenalty = Math.Abs(fps - requestedFps) * 1000.0;
                        return sizePenalty + fpsPenalty;
                    })
                    .FirstOrDefault();
                if (requested is not null && requestedWidth > 0 && requestedHeight > 0 && requestedFps > 0)
                {
                    await source.SetFormatAsync(requested);
                    var actualFps = requested.FrameRate.Denominator == 0 ? 0 : (double)requested.FrameRate.Numerator / requested.FrameRate.Denominator;
                    Description = $"Media Foundation camera · {requested.VideoFormat.Width}×{requested.VideoFormat.Height} · {actualFps:F1} fps";
                }
                var reader = await capture.CreateFrameReaderAsync(source, MediaEncodingSubtypes.Bgra8);
                reader.AcquisitionMode = MediaFrameReaderAcquisitionMode.Realtime;
                reader.FrameArrived += Reader_FrameArrived;
                var status = await reader.StartAsync();
                if (status != MediaFrameReaderStartStatus.Success)
                {
                    reader.FrameArrived -= Reader_FrameArrived;
                    reader.Dispose();
                    throw new InvalidOperationException($"Media Foundation frame reader failed to start: {status}.");
                }
                _capture = capture;
                _reader = reader;
                _running = true;
                var devices = await ListDevicesAsync().ConfigureAwait(false);
                var name = devices.FirstOrDefault(device => device.Id == deviceId)?.Name;
                if (!string.IsNullOrWhiteSpace(name)) Description = $"{name} · {Description}";
            }
            catch
            {
                capture.Dispose();
                throw;
            }
        }
        finally { _lifecycle.Release(); }
    }

    private void Reader_FrameArrived(MediaFrameReader sender, MediaFrameArrivedEventArgs args)
    {
        if (!_running || Interlocked.Exchange(ref _copyingFrame, 1) != 0) return;
        try
        {
            using var frame = sender.TryAcquireLatestFrame();
            var original = frame?.VideoMediaFrame?.SoftwareBitmap;
            if (original is null) return;
            SoftwareBitmap? converted = null;
            var bitmap = original;
            if (bitmap.BitmapPixelFormat != BitmapPixelFormat.Bgra8 || bitmap.BitmapAlphaMode != BitmapAlphaMode.Premultiplied)
            {
                converted = SoftwareBitmap.Convert(bitmap, BitmapPixelFormat.Bgra8, BitmapAlphaMode.Premultiplied);
                bitmap = converted;
            }
            try
            {
                var byteCount = checked(bitmap.PixelWidth * bitmap.PixelHeight * 4);
                var pixels = new byte[byteCount];
                var buffer = new global::Windows.Storage.Streams.Buffer((uint)byteCount);
                bitmap.CopyToBuffer(buffer);
                using var dataReader = DataReader.FromBuffer(buffer);
                dataReader.ReadBytes(pixels);
                var sequence = Interlocked.Increment(ref _sequence) - 1;
                FrameReady?.Invoke(this, new VideoFrame(sequence, Stopwatch.GetTimestamp(), bitmap.PixelWidth, bitmap.PixelHeight, pixels));
            }
            finally { converted?.Dispose(); }
        }
        catch (ObjectDisposedException) { }
        finally { Volatile.Write(ref _copyingFrame, 0); }
    }

    public async Task StopAsync(TimeSpan timeout)
    {
        await _lifecycle.WaitAsync().WaitAsync(timeout).ConfigureAwait(false);
        try
        {
            _running = false;
            var reader = _reader;
            var capture = _capture;
            _reader = null;
            _capture = null;
            if (reader is not null)
            {
                reader.FrameArrived -= Reader_FrameArrived;
                try { await reader.StopAsync().AsTask().WaitAsync(timeout).ConfigureAwait(false); }
                finally { reader.Dispose(); }
            }
            capture?.Dispose();
        }
        finally { _lifecycle.Release(); }
    }

    public async ValueTask DisposeAsync()
    {
        try { await StopAsync(TimeSpan.FromSeconds(2)).ConfigureAwait(false); }
        finally { _lifecycle.Dispose(); }
    }
}
