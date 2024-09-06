using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using System.Text.Json;
using System.Threading.Tasks;

namespace TestServer
{
    internal static class ObjectExtensions
    {
        public static object? ToDocumentObject(this object? obj)
        {
            if (obj == null) return null;

            if(obj is JsonElement json) {
                switch(json.ValueKind) {
                    case JsonValueKind.Array: {
                        var retVal = new List<object?>();
                        foreach(var subelement in json.EnumerateArray()) {
                            retVal.Add(ToDocumentObject(subelement));
                        }

                        return retVal;
                    }
                    case JsonValueKind.Object: {
                        var retVal = new Dictionary<string, object?>();
                        foreach(var subelement in json.EnumerateObject()) {
                            retVal[subelement.Name] = ToDocumentObject(subelement.Value);
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
                }
            }

            return obj;
        }
    }
}
