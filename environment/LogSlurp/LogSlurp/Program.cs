using System.Text.Json.Serialization;

var builder = WebApplication.CreateSlimBuilder(args);

builder.Services.AddControllers();

var app = builder.Build();

app.UseWebSockets();
app.MapControllers();
app.Run();
