using System.Diagnostics;

namespace LongJumpReplay.Core;

public enum PlaybackMode
{
    Live,
    Replay
}

public sealed record VideoFrame(long Sequence, long TimestampTicks, int Width, int Height, byte[] Bgra32);

public sealed record ReplayState(PlaybackMode Mode, long? DisplayedSequence, long? FreezeSequence, int BufferedFrames);

/// <summary>
/// UI-independent Live/Freeze/Replay state. Capture never stops while replay is frozen.
/// </summary>
public sealed class ReplayCoordinator
{
    private readonly object _gate = new();
    private readonly LinkedList<VideoFrame> _frames = [];
    private readonly long _retentionTicks;
    private readonly int _maxFrames;
    private LinkedListNode<VideoFrame>? _displayed;
    private long? _freezeSequence;

    public ReplayCoordinator(TimeSpan retention, int maxFrames = 600)
    {
        if (retention <= TimeSpan.Zero) throw new ArgumentOutOfRangeException(nameof(retention));
        if (maxFrames < 2) throw new ArgumentOutOfRangeException(nameof(maxFrames));
        _retentionTicks = (long)(retention.TotalSeconds * Stopwatch.Frequency);
        _maxFrames = maxFrames;
    }

    public PlaybackMode Mode { get; private set; } = PlaybackMode.Live;

    public void OnFrame(VideoFrame frame)
    {
        ArgumentNullException.ThrowIfNull(frame);
        lock (_gate)
        {
            _frames.AddLast(frame);
            if (Mode == PlaybackMode.Live) _displayed = _frames.Last;
            var cutoff = frame.TimestampTicks - _retentionTicks;
            while (_frames.Count > _maxFrames || (_frames.First is not null && _frames.First.Value.TimestampTicks < cutoff))
            {
                var removed = _frames.First!;
                if (ReferenceEquals(removed, _displayed) && Mode == PlaybackMode.Replay) break;
                _frames.RemoveFirst();
            }
        }
    }

    public bool Freeze()
    {
        lock (_gate)
        {
            if (_frames.Last is null) return false;
            Mode = PlaybackMode.Replay;
            _displayed = _frames.Last;
            _freezeSequence = _displayed.Value.Sequence;
            return true;
        }
    }

    public void ReturnLive()
    {
        lock (_gate)
        {
            Mode = PlaybackMode.Live;
            _displayed = _frames.Last;
            _freezeSequence = null;
        }
    }

    public VideoFrame? Step(int delta)
    {
        lock (_gate)
        {
            if (Mode != PlaybackMode.Replay || _displayed is null || delta == 0) return _displayed?.Value;
            var node = _displayed;
            var count = Math.Abs(delta);
            while (count-- > 0)
            {
                var next = delta < 0 ? node.Previous : node.Next;
                if (next is null) break;
                node = next;
            }
            _displayed = node;
            return node.Value;
        }
    }

    public VideoFrame? DisplayedFrame()
    {
        lock (_gate) return _displayed?.Value;
    }

    public ReplayState Snapshot()
    {
        lock (_gate) return new ReplayState(Mode, _displayed?.Value.Sequence, _freezeSequence, _frames.Count);
    }
}
