using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;

namespace ClientC
{
    internal static class HistoryManager
    {
        public const string HistoryDirectory = "chat_history";

        public static void EnsureHistoryDirectory(string path = null)
        {
            string target = path ?? HistoryDirectory;
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

            StringBuilder builder = new StringBuilder();
            foreach (char ch in name)
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

            string result = builder.ToString().Trim('_');
            return string.IsNullOrEmpty(result) ? fallback : result;
        }

        public static string HistoryPath(string room, string serverKey = "default")
        {
            EnsureHistoryDirectory();
            string safeServer = SanitizeName(serverKey, "default");
            string serverDir = Path.Combine(HistoryDirectory, safeServer);
            EnsureHistoryDirectory(serverDir);
            string safeRoom = SanitizeName(room, "room");
            return Path.Combine(serverDir, safeRoom + ".txt");
        }

        public static string[] TailLines(string filePath, int count, out int startIndex)
        {
            startIndex = 0;
            if (!File.Exists(filePath))
            {
                return Array.Empty<string>();
            }

            string[] lines = File.ReadAllLines(filePath);
            int total = lines.Length;
            startIndex = Math.Max(0, total - count);
            return lines.Skip(startIndex).ToArray();
        }

        public static string[] HeadChunk(string filePath, int startIndex, int chunk, out int newStart)
        {
            newStart = 0;
            if (!File.Exists(filePath))
            {
                return Array.Empty<string>();
            }

            string[] lines = File.ReadAllLines(filePath);
            newStart = Math.Max(0, startIndex - chunk);
            return lines.Skip(newStart).Take(startIndex - newStart).ToArray();
        }

        public static void AppendHistoryLine(string room, string text, string serverKey = "default")
        {
            string path = HistoryPath(room, serverKey);
            EnsureHistoryDirectory(Path.GetDirectoryName(path));
            using (StreamWriter writer = new StreamWriter(path, true, Encoding.UTF8))
            {
                if (!text.EndsWith("\n"))
                {
                    writer.WriteLine(text);
                }
                else
                {
                    writer.Write(text);
                }
            }
        }
    }
}
