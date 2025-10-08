using System;
using System.Collections.Generic;
using System.IO;
using System.Web.Script.Serialization;

namespace ClientC
{
    internal sealed class ServerStore
    {
        private const string ServerFile = "servers.json";

        private readonly Dictionary<string, ServerInfo> _servers = new Dictionary<string, ServerInfo>(StringComparer.OrdinalIgnoreCase);
        private readonly JavaScriptSerializer _serializer = new JavaScriptSerializer();

        public Dictionary<string, ServerInfo> Servers
        {
            get { return _servers; }
        }

        public void Load()
        {
            if (!File.Exists(ServerFile))
            {
                return;
            }

            try
            {
                string json = File.ReadAllText(ServerFile);
                Dictionary<string, ServerInfo> data = _serializer.Deserialize<Dictionary<string, ServerInfo>>(json);
                if (data != null)
                {
                    _servers.Clear();
                    foreach (KeyValuePair<string, ServerInfo> pair in data)
                    {
                        if (!string.IsNullOrWhiteSpace(pair.Key) && pair.Value != null)
                        {
                            _servers[pair.Key] = pair.Value;
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
            string json = _serializer.Serialize(_servers);
            File.WriteAllText(ServerFile, json);
        }
    }

    internal sealed class ServerInfo
    {
        public string Host { get; set; } = "127.0.0.1";
        public int Port { get; set; } = 55555;
    }
}
