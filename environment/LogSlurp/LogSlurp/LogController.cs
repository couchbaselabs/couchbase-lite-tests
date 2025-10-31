using Microsoft.AspNetCore.Mvc;
using System.Net.WebSockets;
using System.Text.Json.Serialization;

namespace LogSlurp
{
    public readonly record struct StartNewLogBody(string log_id);

    public sealed class LogController : ControllerBase
    {
        private const string LogIDHeader = "CBL-Log-ID";
        private const string LogIDParam = "cbl_log_id";
        private const string LogTagHeader = "CBL-Log-Tag";
        private const string LogTagParam = "cbl_log_tag";

        private static readonly Dictionary<string, SerializedStreamWriter> FileLoggers = new();

        [Route("/openLogStream")]
        [HttpGet]
        public async Task OpenLogStream()
        {
            if(HttpContext.WebSockets.IsWebSocketRequest) {
                var id = await GetLogID();
                if(id == null) {
                    return;
                }

                var tag = HttpContext.Request.Headers[LogTagHeader].FirstOrDefault()
                    ?? HttpContext.Request.Query[LogTagParam].FirstOrDefault();
                if (String.IsNullOrEmpty(tag)) {
                    tag = "{0} ";
                } else {
                    tag += ": {0} ";
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
        public async Task StartNewLog([FromBody]StartNewLogBody body)
        {
            if(!ModelState.IsValid) {
                HttpContext.Response.StatusCode = StatusCodes.Status400BadRequest;
                foreach(var state in ModelState) {
                    foreach(var err in state.Value.Errors) {
                        await HttpContext.Response.WriteAsync(err.ErrorMessage);
                    }
                }
                return;
            }

            if(FileLoggers.ContainsKey(body.log_id)) {
                HttpContext.Response.StatusCode = StatusCodes.Status400BadRequest;
                await HttpContext.Response.WriteAsync($"Log with id '{body.log_id}' already started!");
                return;
            }

            Directory.CreateDirectory(Path.Combine(Path.GetTempPath(), "logslurp"));
            var stream = System.IO.File.Open(Path.Combine(Path.GetTempPath(), "logslurp", $"{body.log_id}.txt"),
                FileMode.CreateNew, 
                FileAccess.Write,
                FileShare.Read);

            FileLoggers[body.log_id] = new SerializedStreamWriter(stream);
        }

        [Route("/finishLog")]
        [HttpPost]
        public async Task FinishLog()
        {
            var id = await GetLogID();
            if (id == null) {
                return;
            }

            if(!FileLoggers.Remove(id, out var writer)) {
                HttpContext.Response.StatusCode = StatusCodes.Status500InternalServerError;
                await HttpContext.Response.WriteAsync("Log removal failed");
                return;
            }

            await writer.DisposeAsync();
        }

        [Route("/retrieveLog")]
        [HttpGet]
        public async Task<ActionResult> RetrieveLog()
        {
            var id = HttpContext.Request.Headers[LogIDHeader].FirstOrDefault()
                ?? HttpContext.Request.Query[LogIDParam];
            if (String.IsNullOrEmpty(id)) {
                HttpContext.Response.StatusCode = StatusCodes.Status400BadRequest;
                await HttpContext.Response.WriteAsync($"Missing header '{LogIDHeader}' or query parameter '{LogIDParam}'");
                return BadRequest();
            }

            if (FileLoggers.TryGetValue(id, out var writer)) {
                await writer.FlushAsync();
            }

            var stream = System.IO.File.Open(Path.Combine(Path.GetTempPath(), "logslurp", $"{id}.txt"),
                FileMode.Open,
                FileAccess.Read,
                FileShare.ReadWrite);

            return File(stream, "text/plain");
        }

        private async Task<string?> GetLogID()
        {
            var id = HttpContext.Request.Headers[LogIDHeader].FirstOrDefault()
                ?? HttpContext.Request.Query[LogIDParam];
            if (String.IsNullOrEmpty(id)) {
                HttpContext.Response.StatusCode = StatusCodes.Status400BadRequest;
                await HttpContext.Response.WriteAsync($"Missing header '{LogIDHeader}' or query parameter '{LogIDParam}'");
                return null;
            }

            if (FileLoggers.ContainsKey(id)) {
                return id;
            }
            
            HttpContext.Response.StatusCode = StatusCodes.Status400BadRequest;
            await HttpContext.Response.WriteAsync($"Unknown Log ID '{id}'");
            return null;
        }

        private static async Task ReadLogs(WebSocket ws, string id, string prologueFormat)
        {
            var writer = FileLoggers[id];
            var buffer = new byte[1024 * 4];
            var receiveResult = await ws.ReceiveAsync(buffer, CancellationToken.None);
            while(!receiveResult.CloseStatus.HasValue) {
                var now = DateTimeOffset.UtcNow.ToString("yyyy-MM-dd HH:mm:ss,fff");
                await writer.WriteAsync(String.Format(prologueFormat, now), buffer.Take(receiveResult.Count).Select(x => (char)x).ToArray());
                receiveResult = await ws.ReceiveAsync(buffer, CancellationToken.None);
            }

            await ws.CloseAsync(receiveResult.CloseStatus.Value, receiveResult.CloseStatusDescription, CancellationToken.None);
        }
    }
}
