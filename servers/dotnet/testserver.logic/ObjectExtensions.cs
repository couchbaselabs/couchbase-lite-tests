using System.Text.Json;

namespace TestServer
{
    internal static class ObjectExtensions
    {
        public static object? ToDocumentObject(this object? obj)
        {
            switch (obj)
            {
                case null:
                    return null;
                case JsonElement json:
                    switch(json.ValueKind) {
                        case JsonValueKind.Array:
                        {
                            return json.EnumerateArray().Select(subelement => subelement.ToDocumentObject()).ToList();
                        }
                        case JsonValueKind.Object: {
                            var retVal = new Dictionary<string, object?>();
                            foreach(var subelement in json.EnumerateObject()) {
                                retVal[subelement.Name] = subelement.Value.ToDocumentObject();
                            }

                            return retVal;
                        }
                        case JsonValueKind.String:
                            return json.GetString();
                        case JsonValueKind.Number:
                            if(json.TryGetInt64(out var integral)) {
                                return integral;
                            }

                            return json.GetDouble();
                        case JsonValueKind.True:
                        case JsonValueKind.False:
                            return json.GetBoolean();
                        case JsonValueKind.Null:
                            return null;
                        case JsonValueKind.Undefined:
                            break;
                        default:
                            throw new ArgumentOutOfRangeException(nameof(obj));
                    }

                    break;
            }

            return obj;
        }
    }
}
