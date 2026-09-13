using System.IO.MemoryMappedFiles;
using System.Text.Json;
using LongJumpReplay.Core;
using LongJumpReplay.Video.Windows;

const int ControlBytes = 32;
const int SlotHeaderBytes = 32;
const int SlotCount = 3;

var options = Arguments.Parse(args);
var devices = await MediaFoundationCameraSource.ListDevicesAsync();
if (options.DeviceIndex < 0 || options.DeviceIndex >= devices.Count)
    throw new ArgumentOutOfRangeException(nameof(options.DeviceIndex), $"Camera index {options.DeviceIndex} is unavailable.");

await using var source = new MediaFoundationCameraSource(devices[options.DeviceIndex].Id, options.Width, options.Height, options.Fps);
MemoryMappedFile? mapping = null;
MemoryMappedViewAccessor? view = null;
var mapName = $"LongJumpReplay.Capture.{Environment.ProcessId}.{Guid.NewGuid():N}";
var gate = new object();

source.FrameReady += (_, frame) =>
{
    lock (gate)
    {
        if (mapping is null)
        {
            var slotBytes = checked(SlotHeaderBytes + frame.Bgra32.Length);
            mapping = MemoryMappedFile.CreateNew(mapName, checked(ControlBytes + (long)SlotCount * slotBytes));
            view = mapping.CreateViewAccessor();
            view.Write(0, 0x4C4A5246); // LJRF
            view.Write(4, 1);
            view.Write(8, SlotCount);
            view.Write(12, slotBytes);
            view.Write(16, -1L);
            Console.WriteLine(JsonSerializer.Serialize(new { type = "ready", map = mapName, frame.Width, frame.Height, slotBytes, slots = SlotCount, source = source.Description }));
            Console.Out.Flush();
        }
        var currentView = view!;
        var slotSize = SlotHeaderBytes + frame.Bgra32.Length;
        var slot = (int)(frame.Sequence % SlotCount);
        var offset = ControlBytes + (long)slot * slotSize;
        currentView.Write(offset + 8, frame.TimestampTicks);
        currentView.Write(offset + 16, frame.Width);
        currentView.Write(offset + 20, frame.Height);
        currentView.Write(offset + 24, frame.Bgra32.Length);
        currentView.WriteArray(offset + SlotHeaderBytes, frame.Bgra32, 0, frame.Bgra32.Length);
        currentView.Write(offset, frame.Sequence);
        currentView.Write(16, frame.Sequence);
    }
};

using var stop = new CancellationTokenSource();
Console.CancelKeyPress += (_, eventArgs) => { eventArgs.Cancel = true; stop.Cancel(); };
try
{
    await source.StartAsync(stop.Token);
    var input = Console.In.ReadLineAsync(stop.Token);
    await input;
}
catch (OperationCanceledException) { }
finally
{
    await source.StopAsync(TimeSpan.FromSeconds(2));
    view?.Dispose();
    mapping?.Dispose();
}

internal sealed record Arguments(int DeviceIndex, int Width, int Height, double Fps)
{
    public static Arguments Parse(string[] values)
    {
        var index = Array.IndexOf(values, "--device");
        var width = Array.IndexOf(values, "--width");
        var height = Array.IndexOf(values, "--height");
        var fps = Array.IndexOf(values, "--fps");
        return new Arguments(
            index >= 0 ? int.Parse(values[index + 1]) : 0,
            width >= 0 ? int.Parse(values[width + 1]) : 1280,
            height >= 0 ? int.Parse(values[height + 1]) : 720,
            fps >= 0 ? double.Parse(values[fps + 1], System.Globalization.CultureInfo.InvariantCulture) : 120);
    }
}
