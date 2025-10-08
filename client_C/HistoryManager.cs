using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;

namespace ClientC;

internal static class HistoryManager
{
    public const string HistoryDirectory = "chat_history";

    public static void EnsureHistoryDirectory(string? path = null)
    {
        var target = path ?? HistoryDirectory;
        if (!Directory.Exists(target))
        {
            Directory.CreateDirectory(target);
        }
    }

    private static string SanitizeName(string name, string fallback)
    {
        if (string.IsNullOrWhiteSpace(name))
        {
            return fallback;
        }

        var builder = new StringBuilder();
        foreach (var ch in name)
        {
            if (char.IsLetterOrDigit(ch) || ch == '_' || ch == '-' || ch == '.' || ch == '@')
            {
                builder.Append(ch);
            }
            else if (char.IsWhiteSpace(ch))
            {
                builder.Append('_');
            }
            else
            {
                builder.Append('_');
            }
        }

        var result = builder.ToString().Trim('_');
        return string.IsNullOrEmpty(result) ? fallback : result;
    }

    public static string HistoryPath(string room, string serverKey = "default")
    {
        EnsureHistoryDirectory();
        var safeServer = SanitizeName(serverKey, "default");
        var serverDir = Path.Combine(HistoryDirectory, safeServer);
        EnsureHistoryDirectory(serverDir);
        var safeRoom = SanitizeName(room, "room");
        return Path.Combine(serverDir, safeRoom + ".txt");
    }

    public static (IReadOnlyList<string> Lines, int StartIndex) TailLines(string filePath, int count)
    {
        if (!File.Exists(filePath))
        {
            return (Array.Empty<string>(), 0);
        }

        var lines = File.ReadAllLines(filePath);
        var total = lines.Length;
        var start = Math.Max(0, total - count);
        return (lines.Skip(start).ToArray(), start);
    }

    public static (IReadOnlyList<string> Lines, int NewStart) HeadChunk(string filePath, int startIndex, int chunk)
    {
        if (!File.Exists(filePath))
        {
            return (Array.Empty<string>(), 0);
        }

        var lines = File.ReadAllLines(filePath);
        var newStart = Math.Max(0, startIndex - chunk);
        var slice = lines.Skip(newStart).Take(startIndex - newStart).ToArray();
        return (slice, newStart);
    }

    public static void AppendHistoryLine(string room, string text, string serverKey = "default")
    {
        var path = HistoryPath(room, serverKey);
        EnsureHistoryDirectory(Path.GetDirectoryName(path));
        using var writer = new StreamWriter(path, append: true, Encoding.UTF8);
        if (!text.EndsWith('\n'))
        {
            writer.WriteLine(text);
        }
        else
        {
            writer.Write(text);
        }
    }
}
