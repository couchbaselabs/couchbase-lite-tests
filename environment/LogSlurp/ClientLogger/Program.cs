
using ClientLogger;
using System.Net.WebSockets;
using System.Text;
using System.Text.Json;

const int Port = 5186;

using var httpClient = new HttpClient();
var response = await httpClient.PostAsync($"http://localhost:{Port}/startNewLog", null);
var responseContent = await response.Content.ReadAsStreamAsync();
var responseObject = await JsonSerializer.DeserializeAsync<StartNewLogResponse>(responseContent);

var ws = new ClientWebSocket();
ws.Options.SetRequestHeader("CBL-Log-ID", responseObject.log_id);
ws.Options.SetRequestHeader("CBL-Log-Tag", "ClientLogger");
await ws.ConnectAsync(new Uri($"ws://localhost:{Port}/openLogStream"), CancellationToken.None);

Console.WriteLine("Begin typing (type quit to quit)");
var next = Console.ReadLine();
while(next != null && next != "quit") {
    await ws.SendAsync(Encoding.ASCII.GetBytes(next), WebSocketMessageType.Text, true, CancellationToken.None);
    next = Console.ReadLine();
}

await ws.CloseAsync(WebSocketCloseStatus.NormalClosure, null, CancellationToken.None);

httpClient.DefaultRequestHeaders.Add("CBL-Log-ID", responseObject.log_id);
response = await httpClient.PostAsync($"http://localhost:{Port}/finishLog", null);
response.EnsureSuccessStatusCode();

var logString = await httpClient.GetStringAsync($"http://localhost:{Port}/retrieveLog");
Console.WriteLine();
Console.WriteLine("==== Retrieved ====");
Console.WriteLine(logString);