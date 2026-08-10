using System.Text.Json;
using System.Text.Json.Nodes;

namespace LongJumpReplay.Infrastructure;

public sealed record CameraSettings(string SourceType, int DeviceIndex, int Width, int Height, double Fps);

public sealed record CompatibleConfig(CameraSettings Camera, string Language, JsonObject Document)
{
    public static CompatibleConfig Load(string path)
    {
        var document = JsonNode.Parse(File.ReadAllText(path))?.AsObject() ?? throw new InvalidDataException("Configuration root must be an object.");
        var camera = document["camera"]?.AsObject();
        var general = document["general"]?.AsObject();
        return new CompatibleConfig(
            new CameraSettings(
                camera?["source_type"]?.GetValue<string>() ?? "camera",
                camera?["device_index"]?.GetValue<int>() ?? 0,
                camera?["width"]?.GetValue<int>() ?? 1280,
                camera?["height"]?.GetValue<int>() ?? 720,
                camera?["fps"]?.GetValue<double>() ?? 120),
            general?["language"]?.GetValue<string>() ?? "en",
            document);
    }

    public void SaveAtomic(string path)
    {
        var target = Path.GetFullPath(path);
        var directory = Path.GetDirectoryName(target) ?? throw new InvalidOperationException("Configuration directory is unavailable.");
        Directory.CreateDirectory(directory);
        var temporary = target + ".tmp";
        File.WriteAllText(temporary, Document.ToJsonString(new JsonSerializerOptions { WriteIndented = true }));
        if (File.Exists(target))
        {
            var backup = target + ".bak";
            File.Replace(temporary, target, backup, ignoreMetadataErrors: true);
        }
        else File.Move(temporary, target);
    }
}
