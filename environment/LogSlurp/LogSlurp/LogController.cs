﻿using Microsoft.AspNetCore.Mvc;
using System.Net.WebSockets;

namespace LogSlurp
{
    public sealed class LogController : ControllerBase
    {
        private const string LogIDHeader = "CBL-Log-ID";
        private const string LogTagHeader = "CBL-Log-Tag";

        private static readonly Dictionary<string, TextWriter> FileLoggers = new();

        [Route("/openLogStream")]
        [HttpGet]
        public async Task OpenLogStream()
        {
            if(HttpContext.WebSockets.IsWebSocketRequest) {
                var id = await GetLogID(true);
                if(id == null) {
                    return;
                }

                var tag = HttpContext.Request.Headers[LogTagHeader].FirstOrDefault();
                if (tag == null || tag == String.Empty) {
                    tag = "";
                } else {
                    tag += ": ";
                }

                var ws = await HttpContext.WebSockets.AcceptWebSocketAsync();
                await ReadLogs(ws, id, tag);
            } else {
                HttpContext.Response.StatusCode = StatusCodes.Status400BadRequest;
                await HttpContext.Response.WriteAsync("Non websocket request received");
            }
        }

        [Route("/startNewLog")]
        [HttpPost]
        public ActionResult StartNewLog()
        {
            var id = Guid.NewGuid().ToString();
            Directory.CreateDirectory(Path.Combine(Path.GetTempPath(), "logslurp"));
            var stream = System.IO.File.Open(Path.Combine(Path.GetTempPath(), "logslurp", $"{id}.txt"),
                FileMode.CreateNew, 
                FileAccess.Write,
                FileShare.Read);

            FileLoggers[id] = new StreamWriter(stream);
            return new JsonResult(new { log_id = id });
        }

        [Route("/finishLog")]
        [HttpPost]
        public async Task FinishLog()
        {
            var id = await GetLogID(true);
            if (id == null) {
                return;
            }

            if(!FileLoggers.Remove(id, out var writer)) {
                HttpContext.Response.StatusCode = StatusCodes.Status500InternalServerError;
                await HttpContext.Response.WriteAsync("Log removal failed");
                return;
            }

            writer.Dispose();
        }

        [Route("/retrieveLog")]
        [HttpGet]
        public async Task<ActionResult> RetrieveLog()
        {
            var id = await GetLogID(false);
            if (id == null) {
                return BadRequest();
            }

            var stream = System.IO.File.Open(Path.Combine(Path.GetTempPath(), "logslurp", $"{id}.txt"),
                FileMode.Open,
                FileAccess.Read,
                FileShare.ReadWrite);

            return File(stream, "text/plain");
        }

        private async Task<string?> GetLogID(bool mustExist)
        {
            var id = HttpContext.Request.Headers[LogIDHeader].FirstOrDefault();
            if (id == null || id == String.Empty) {
                HttpContext.Response.StatusCode = StatusCodes.Status400BadRequest;
                await HttpContext.Response.WriteAsync($"Missing header '{LogIDHeader}'");
                return null;
            }

            if (mustExist && !FileLoggers.ContainsKey(id)) {
                HttpContext.Response.StatusCode = StatusCodes.Status400BadRequest;
                await HttpContext.Response.WriteAsync($"Unknown Log ID '{id}'");
                return null;
            }

            return id;
        }

        private static async Task ReadLogs(WebSocket ws, string id, string? tag)
        {
            var writer = FileLoggers[id];
            var buffer = new byte[1024 * 4];
            var receiveResult = await ws.ReceiveAsync(buffer, CancellationToken.None);
            while(!receiveResult.CloseStatus.HasValue) {
                await writer.WriteAsync(tag);
                await writer.WriteLineAsync(buffer.Take(receiveResult.Count).Select(x => (char)x).ToArray());
                receiveResult = await ws.ReceiveAsync(buffer, CancellationToken.None);
            }

            await ws.CloseAsync(receiveResult.CloseStatus.Value, receiveResult.CloseStatusDescription, CancellationToken.None);
        }
    }
}
