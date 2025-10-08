using System;
using System.Collections.Generic;
using System.IO;
using System.Text.Json;

namespace ClientC;

internal sealed class ServerStore
{
    private const string ServerFile = "servers.json";

    public Dictionary<string, ServerInfo> Servers { get; } = new(StringComparer.OrdinalIgnoreCase);

    public void Load()
    {
        if (!File.Exists(ServerFile))
        {
            return;
        }

        try
        {
            var json = File.ReadAllText(ServerFile);
            var data = JsonSerializer.Deserialize<Dictionary<string, ServerInfo>>(json);
            if (data != null)
            {
                Servers.Clear();
                foreach (var pair in data)
                {
                    if (!string.IsNullOrWhiteSpace(pair.Key) && pair.Value != null)
                    {
                        Servers[pair.Key] = pair.Value;
                    }
                }
            }
        }
        catch
        {
            // Ignorar errores de parsing.
        }
    }

    public void Save()
    {
        var options = new JsonSerializerOptions
        {
            WriteIndented = true
        };
        File.WriteAllText(ServerFile, JsonSerializer.Serialize(Servers, options));
    }
}

internal sealed class ServerInfo
{
    public string Host { get; set; } = "127.0.0.1";
    public int Port { get; set; } = 55555;
}
