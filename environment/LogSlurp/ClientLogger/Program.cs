
using ClientLogger;
using System.Net.WebSockets;
using System.Text;
using System.Text.Json;

using var httpClient = new HttpClient();
var response = await httpClient.PostAsync("http://localhost:8180/startNewLog", null);
var responseContent = await response.Content.ReadAsStreamAsync();
var responseObject = await JsonSerializer.DeserializeAsync<StartNewLogResponse>(responseContent);

var ws = new ClientWebSocket();
ws.Options.SetRequestHeader("CBL-Log-ID", responseObject.log_id);
ws.Options.SetRequestHeader("CBL-Log-Tag", "ClientLogger");
await ws.ConnectAsync(new Uri("ws://localhost:8180/openLogStream"), CancellationToken.None);

Console.WriteLine("Begin typing (type quit to quit)");
var next = Console.ReadLine();
while(next != null && next != "quit") {
    await ws.SendAsync(Encoding.ASCII.GetBytes(next), WebSocketMessageType.Text, true, CancellationToken.None);
    next = Console.ReadLine();
}

await ws.CloseAsync(WebSocketCloseStatus.NormalClosure, null, CancellationToken.None);

httpClient.DefaultRequestHeaders.Add("CBL-Log-ID", responseObject.log_id);
response = await httpClient.PostAsync("http://localhost:8180/finishLog", null);
response.EnsureSuccessStatusCode();

var logString = await httpClient.GetStringAsync("http://localhost:8180/retrieveLog");
Console.WriteLine();
Console.WriteLine("==== Retrieved ====");
Console.WriteLine(logString);