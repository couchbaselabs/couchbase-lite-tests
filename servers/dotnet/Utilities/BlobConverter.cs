using Couchbase.Lite;
using sly.lexer;
using System;
using System.Collections.Generic;
using System.Data;
using System.Linq;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;
using System.Threading.Tasks;

namespace TestServer.Utilities
{
    internal sealed class BlobConverter : JsonConverter<Blob>
    {
        public override Blob? Read(ref Utf8JsonReader reader, Type typeToConvert, JsonSerializerOptions options)
        {
            throw new NotImplementedException();
        }

        public override void Write(Utf8JsonWriter writer, Blob value, JsonSerializerOptions options)
        {
            writer.WriteStartObject();
            writer.WriteString("@type", "blob");
            writer.WriteString("content_type", value.ContentType);
            if (value.Length > 0) {
                writer.WriteNumber("length", value.Length);
            }

            if(value.Digest != null) {
                writer.WriteString("digest", value.Digest);
            }

            writer.WriteEndObject();
        }
    }
}
