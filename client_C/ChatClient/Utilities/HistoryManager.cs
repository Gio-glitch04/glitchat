using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;

namespace ChatClient
{
    internal static class HistoryManager
    {
        public const string HistoryDirectory = "chat_history";

        public static void EnsureHistoryDirectory(string path = null)
        {
            var target = string.IsNullOrWhiteSpace(path) ? HistoryDirectory : path;
            if (!Directory.Exists(target))
            {
                Directory.CreateDirectory(target);
            }
        }

        private static string Sanitize(string name, string fallback)
        {
            if (string.IsNullOrEmpty(name))
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

            var sanitized = builder.ToString().Trim('_');
            return string.IsNullOrEmpty(sanitized) ? fallback : sanitized;
        }

        public static string HistoryPath(string room, string serverKey = "default")
        {
            EnsureHistoryDirectory();
            var safeServer = Sanitize(serverKey, "default");
            var serverDir = Path.Combine(HistoryDirectory, safeServer);
            EnsureHistoryDirectory(serverDir);
            var safeRoom = Sanitize(room, "room");
            return Path.Combine(serverDir, safeRoom + ".txt");
        }

        public static Tuple<List<string>, int> TailLines(string filepath, int n)
        {
            if (!File.Exists(filepath))
            {
                return Tuple.Create(new List<string>(), 0);
            }

            var rawLines = File.ReadAllLines(filepath, Encoding.UTF8).ToList();
            var total = rawLines.Count;
            var start = Math.Max(0, total - n);
            var result = rawLines.Skip(start).Select(l => l + Environment.NewLine).ToList();
            return Tuple.Create(result, start);
        }

        public static Tuple<List<string>, int> HeadChunk(string filepath, int startIndex, int chunk)
        {
            if (!File.Exists(filepath))
            {
                return Tuple.Create(new List<string>(), 0);
            }

            var rawLines = File.ReadAllLines(filepath, Encoding.UTF8).ToList();
            var newStart = Math.Max(0, startIndex - chunk);
            var result = rawLines.Skip(newStart).Take(startIndex - newStart).Select(l => l + Environment.NewLine).ToList();
            return Tuple.Create(result, newStart);
        }

        public static void AppendHistoryLine(string room, string line, string serverKey)
        {
            var path = HistoryPath(room, serverKey);
            EnsureHistoryDirectory(Path.GetDirectoryName(path));
            using (var writer = new StreamWriter(path, true, Encoding.UTF8))
            {
                if (!line.EndsWith("\n"))
                {
                    writer.WriteLine(line);
                }
                else
                {
                    writer.Write(line);
                }
            }
        }
    }
}
