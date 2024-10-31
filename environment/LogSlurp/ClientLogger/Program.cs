
using ClientLogger;
using System.Net.Http.Json;
using System.Net.WebSockets;
using System.Text;

const int Port = 5186;

using var httpClient = new HttpClient();
var log_id = Guid.NewGuid().ToString();
var response = await httpClient.PostAsync($"http://localhost:{Port}/startNewLog", JsonContent.Create(new { log_id }));
Console.WriteLine();
Console.WriteLine("Session ID: " + log_id);

var ws = new ClientWebSocket();
ws.Options.SetRequestHeader("CBL-Log-ID", log_id);
ws.Options.SetRequestHeader("CBL-Log-Tag", "ClientLogger");
await ws.ConnectAsync(new Uri($"ws://localhost:{Port}/openLogStream"), CancellationToken.None);

Console.WriteLine("Begin typing (type quit to quit)");
var next = Console.ReadLine();
while(next != null && next != "quit") {
    await ws.SendAsync(Encoding.ASCII.GetBytes(next), WebSocketMessageType.Text, true, CancellationToken.None);
    next = Console.ReadLine();
}

await ws.CloseAsync(WebSocketCloseStatus.NormalClosure, null, CancellationToken.None);

httpClient.DefaultRequestHeaders.Add("CBL-Log-ID", log_id);
response = await httpClient.PostAsync($"http://localhost:{Port}/finishLog", null);
response.EnsureSuccessStatusCode();

var logString = await httpClient.GetStringAsync($"http://localhost:{Port}/retrieveLog");
Console.WriteLine();
Console.WriteLine("==== Retrieved ====");
Console.WriteLine(logString);
