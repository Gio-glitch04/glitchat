using System;
using System.Collections.Generic;
using System.Text;

namespace ClientC
{
    internal static class CommandLineSplitter
    {
        public static IReadOnlyList<string> Split(string command)
        {
            List<string> result = new List<string>();
            if (string.IsNullOrWhiteSpace(command))
            {
                return result;
            }

            StringBuilder sb = new StringBuilder();
            bool inQuotes = false;
            char quoteChar = '\0';
            bool escape = false;

            foreach (char ch in command)
            {
                if (escape)
                {
                    sb.Append(ch);
                    escape = false;
                    continue;
                }

                if (ch == '\\')
                {
                    escape = true;
                    continue;
                }

                if (inQuotes)
                {
                    if (ch == quoteChar)
                    {
                        inQuotes = false;
                    }
                    else
                    {
                        sb.Append(ch);
                    }
                    continue;
                }

                if (ch == '\'' || ch == '\"')
                {
                    inQuotes = true;
                    quoteChar = ch;
                    continue;
                }

                if (char.IsWhiteSpace(ch))
                {
                    if (sb.Length > 0)
                    {
                        result.Add(sb.ToString());
                        sb.Clear();
                    }
                    continue;
                }

                sb.Append(ch);
            }

            if (escape)
            {
                sb.Append('\\');
            }

            if (sb.Length > 0)
            {
                result.Add(sb.ToString());
            }

            return result;
        }
    }
}
