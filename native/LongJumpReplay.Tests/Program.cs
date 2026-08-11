using System.Diagnostics;
using System.Text.Json.Nodes;
using LongJumpReplay.Core;
using LongJumpReplay.Infrastructure;
using LongJumpReplay.Video.Windows;

static void AssertTrue(bool value, string message)
{
    if (!value) throw new InvalidOperationException(message);
}

var tests = new List<(string Name, Func<Task> Run)>
{
    ("Freeze keeps capture independent and stepping bounded", () =>
    {
        var replay = new ReplayCoordinator(TimeSpan.FromSeconds(2), 10);
        for (var i = 0; i < 3; i++) replay.OnFrame(new VideoFrame(i, Stopwatch.GetTimestamp() + i, 1, 1, [0, 0, 0, 255]));
        AssertTrue(replay.Freeze(), "Freeze should succeed with frames.");
        replay.OnFrame(new VideoFrame(3, Stopwatch.GetTimestamp() + 3, 1, 1, [0, 0, 0, 255]));
        AssertTrue(replay.Snapshot().FreezeSequence == 2, "Freeze frame must remain selected while capture continues.");
        AssertTrue(replay.Step(-1)?.Sequence == 1, "Previous frame should be reachable.");
        replay.ReturnLive();
        AssertTrue(replay.DisplayedFrame()?.Sequence == 3, "Return Live should select newest frame.");
        return Task.CompletedTask;
    }),
    ("Freeze without a frame fails safely", () =>
    {
        AssertTrue(!new ReplayCoordinator(TimeSpan.FromSeconds(1)).Freeze(), "Empty freeze must fail.");
        return Task.CompletedTask;
    }),
    ("Frame retention is bounded", () =>
    {
        var replay = new ReplayCoordinator(TimeSpan.FromMinutes(1), 3);
        for (var i = 0; i < 8; i++) replay.OnFrame(new VideoFrame(i, Stopwatch.GetTimestamp() + i, 1, 1, [0, 0, 0, 255]));
        AssertTrue(replay.Snapshot().BufferedFrames == 3, "Frame count must honor the configured bound.");
        AssertTrue(replay.DisplayedFrame()?.Sequence == 7, "Live mode must retain the newest frame.");
        return Task.CompletedTask;
    }),
    ("Frozen replay retention remains bounded", () =>
    {
        var replay = new ReplayCoordinator(TimeSpan.FromMinutes(1), 3);
        for (var i = 0; i < 3; i++) replay.OnFrame(new VideoFrame(i, Stopwatch.GetTimestamp() + i, 1, 1, [0, 0, 0, 255]));
        AssertTrue(replay.Freeze(), "Freeze should succeed with frames.");
        for (var i = 3; i < 100; i++) replay.OnFrame(new VideoFrame(i, Stopwatch.GetTimestamp() + i, 1, 1, [0, 0, 0, 255]));
        var snapshot = replay.Snapshot();
        AssertTrue(snapshot.BufferedFrames == 3, "Frozen replay must remain bounded while capture continues.");
        AssertTrue(snapshot.FreezeSequence == 2 && snapshot.DisplayedSequence == 2, "The selected frozen frame must remain available.");
        return Task.CompletedTask;
    }),
    ("Synthetic source starts and stops within bound", async () =>
    {
        await using var source = new SyntheticVideoSource(64, 36, 60);
        var count = 0;
        source.FrameReady += (_, _) => Interlocked.Increment(ref count);
        await source.StartAsync();
        await Task.Delay(150);
        await source.StopAsync(TimeSpan.FromSeconds(1));
        AssertTrue(count >= 4, $"Expected synthetic frames, received {count}.");
        AssertTrue(!source.IsRunning, "Source must be stopped.");
    }),
    ("Existing config remains readable", () =>
    {
        var root = Path.GetFullPath(Path.Combine(AppContext.BaseDirectory, "..", "..", "..", "..", ".."));
        var config = CompatibleConfig.Load(Path.Combine(root, "config.json"));
        AssertTrue(config.Camera.Width > 0 && config.Camera.Height > 0 && config.Camera.Fps > 0, "Camera settings must migrate.");
        return Task.CompletedTask;
    }),
    ("Atomic config save preserves unknown fields and backup", () =>
    {
        var directory = Path.Combine(Path.GetTempPath(), "LongJumpReplay-native-tests", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(directory);
        var path = Path.Combine(directory, "config.json");
        File.WriteAllText(path, "{\"camera\":{\"width\":640,\"future_camera_value\":7},\"future_section\":{\"enabled\":true}}");
        try
        {
            var config = CompatibleConfig.Load(path);
            config.SaveAtomic(path);
            var saved = JsonNode.Parse(File.ReadAllText(path))!.AsObject();
            AssertTrue(saved["future_section"]?["enabled"]?.GetValue<bool>() == true, "Unknown sections must survive a round trip.");
            AssertTrue(saved["camera"]?["future_camera_value"]?.GetValue<int>() == 7, "Unknown camera fields must survive.");
            AssertTrue(File.Exists(path + ".bak"), "Atomic replacement must retain a backup.");
        }
        finally { Directory.Delete(directory, recursive: true); }
        return Task.CompletedTask;
    })
};

var failures = 0;
foreach (var test in tests)
{
    try { await test.Run(); Console.WriteLine($"PASS {test.Name}"); }
    catch (Exception error) { failures++; Console.Error.WriteLine($"FAIL {test.Name}: {error.Message}"); }
}
Console.WriteLine($"Native tests: {tests.Count - failures} passed, {failures} failed");
return failures == 0 ? 0 : 1;
