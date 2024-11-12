using Microsoft.AspNetCore.Mvc;
using System.Net.WebSockets;
using System.Text.Json.Serialization;
using System.Threading.Channels;

namespace LogSlurp
{
    public readonly record struct StartNewLogBody(string log_id);

    public readonly record struct WebSocketLogMessage(string prologueFormat, string id, char[] message);

    public sealed class LogController : ControllerBase
    {
        private const string LogIDHeader = "CBL-Log-ID";
        private const string LogTagHeader = "CBL-Log-Tag";

        private static readonly Dictionary<string, SerializedStreamWriter> FileLoggers = new();

        private Channel<WebSocketLogMessage> LogMessageChannel = Channel.CreateBounded<WebSocketLogMessage>(500);
        private readonly Dictionary<string, Task> WriteTasks = new();

        [Route("/openLogStream")]
        [HttpGet]
        public async Task OpenLogStream()
        {
            if(HttpContext.WebSockets.IsWebSocketRequest) {
                var id = await GetLogID();
                if(id == null) {
                    return;
                }

                var tag = HttpContext.Request.Headers[LogTagHeader].FirstOrDefault();
                if (tag == null || tag == String.Empty) {
                    tag = "{0} ";
                } else {
                    tag += ": {0} ";
                }

                var ws = await HttpContext.WebSockets.AcceptWebSocketAsync().ConfigureAwait(false);
                await ReadLogs(ws, id, tag);
            } else {
                HttpContext.Response.StatusCode = StatusCodes.Status400BadRequest;
                await HttpContext.Response.WriteAsync("Non websocket request received").ConfigureAwait(false);
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
                        await HttpContext.Response.WriteAsync(err.ErrorMessage ?? "<unknown>").ConfigureAwait(false);
                    }
                }
                return;
            }

            if(FileLoggers.ContainsKey(body.log_id)) {
                HttpContext.Response.StatusCode = StatusCodes.Status400BadRequest;
                await HttpContext.Response.WriteAsync($"Log with id '{body.log_id}' already started!").ConfigureAwait(false);
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
                await HttpContext.Response.WriteAsync("Log removal failed").ConfigureAwait(false);
                return;
            }

            await writer.DisposeAsync().ConfigureAwait(false);
        }

        [Route("/retrieveLog")]
        [HttpGet]
        public async Task<ActionResult> RetrieveLog()
        {
            var id = HttpContext.Request.Headers[LogIDHeader].FirstOrDefault();
            if (id == null || id == String.Empty) {
                HttpContext.Response.StatusCode = StatusCodes.Status400BadRequest;
                await HttpContext.Response.WriteAsync($"Missing header '{LogIDHeader}'").ConfigureAwait(false);
                return BadRequest();
            }

            if (FileLoggers.TryGetValue(id, out var writer)) {
                await writer.FlushAsync().ConfigureAwait(false);
            }

            var stream = System.IO.File.Open(Path.Combine(Path.GetTempPath(), "logslurp", $"{id}.txt"),
                FileMode.Open,
                FileAccess.Read,
                FileShare.ReadWrite);

            return File(stream, "text/plain");
        }

        private async Task<string?> GetLogID()
        {
            var id = HttpContext.Request.Headers[LogIDHeader].FirstOrDefault();
            if (id == null || id == String.Empty) {
                HttpContext.Response.StatusCode = StatusCodes.Status400BadRequest;
                await HttpContext.Response.WriteAsync($"Missing header '{LogIDHeader}'").ConfigureAwait(false);
                return null;
            }

            if (!FileLoggers.ContainsKey(id)) {
                HttpContext.Response.StatusCode = StatusCodes.Status400BadRequest;
                await HttpContext.Response.WriteAsync($"Unknown Log ID '{id}'").ConfigureAwait(false);
                return null;
            }

            return id;
        }

        private async Task ReadLogs(WebSocket ws, string id, string prologueFormat)
        {
            var buffer = new byte[1024 * 4];
            var receiveResult = await ws.ReceiveAsync(buffer, CancellationToken.None).ConfigureAwait(false);
            while(!receiveResult.CloseStatus.HasValue) {
                var message = buffer.Take(receiveResult.Count).Select(x => (char)x).ToArray();
                await LogMessageChannel.Writer.WriteAsync(new WebSocketLogMessage(prologueFormat, id, message)).ConfigureAwait(false);
                receiveResult = await ws.ReceiveAsync(buffer, CancellationToken.None).ConfigureAwait(false);
            }

            await ws.CloseAsync(receiveResult.CloseStatus.Value, receiveResult.CloseStatusDescription, CancellationToken.None).ConfigureAwait(false);
        }

        private async void WriteLogMessages(object? id_obj)
        {
            while(true) {
                var next = await LogMessageChannel.Reader.ReadAsync().ConfigureAwait(false);
                if(!FileLoggers.TryGetValue(next.id, out var writer)) {
                    continue;
                }

                var now = DateTimeOffset.UtcNow.ToString("yyyy-MM-dd HH:mm:ss,fff");
                await writer.WriteAsync(String.Format(next.prologueFormat, now), next.message).ConfigureAwait(false);
            }
        }
    }
}
