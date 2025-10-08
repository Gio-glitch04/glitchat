using System;
using System.Collections.Generic;
using System.Text;

namespace ClientC;

internal static class CommandLineSplitter
{
    public static IReadOnlyList<string> Split(string command)
    {
        var result = new List<string>();
        if (string.IsNullOrWhiteSpace(command))
        {
            return result;
        }

        var sb = new StringBuilder();
        var inQuotes = false;
        char quoteChar = '\0';
        var escape = false;

        void Commit()
        {
            if (sb.Length > 0)
            {
                result.Add(sb.ToString());
                sb.Clear();
            }
        }

        foreach (var ch in command)
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
                Commit();
                continue;
            }

            sb.Append(ch);
        }

        if (escape)
        {
            sb.Append('\\');
        }

        Commit();
        return result;
    }
}
