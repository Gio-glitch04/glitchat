using System;
using System.Collections.Generic;
using System.IO;
using System.Text;
using System.Web.Script.Serialization;

namespace ChatClient
{
    internal static class ServerStorage
    {
        public const string ServerFile = "servers.json";
        private static readonly JavaScriptSerializer Serializer = new JavaScriptSerializer();

        public static Dictionary<string, ServerInfo> LoadServers()
        {
            try
            {
                if (!File.Exists(ServerFile))
                {
                    return new Dictionary<string, ServerInfo>();
                }

                var json = File.ReadAllText(ServerFile, Encoding.UTF8);
                if (string.IsNullOrWhiteSpace(json))
                {
                    return new Dictionary<string, ServerInfo>();
                }

                var raw = Serializer.Deserialize<Dictionary<string, ServerInfo>>(json);
                return raw ?? new Dictionary<string, ServerInfo>();
            }
            catch
            {
                return new Dictionary<string, ServerInfo>();
            }
        }

        public static void SaveServers(Dictionary<string, ServerInfo> servers)
        {
            try
            {
                var json = Serializer.Serialize(servers ?? new Dictionary<string, ServerInfo>());
                File.WriteAllText(ServerFile, json, Encoding.UTF8);
            }
            catch (Exception ex)
            {
                Console.WriteLine("Error guardando servers.json: " + ex.Message);
            }
        }
    }

    internal class ServerInfo
    {
        public string Host { get; set; }
        public int Port { get; set; }
    }
}
