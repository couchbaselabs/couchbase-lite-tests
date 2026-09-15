using Couchbase.Lite;

namespace TestServer.Utilities
{
    internal enum PathNodeType
    {
        Dict,
        Array,
        Scalar,
        Missing
    }

    internal sealed class PathNode
    {
        private int? _parentIndex;
        private string? _parentKey;

        public PathNodeType Type { get; }

        public IMutableDictionary Dict => field ?? throw new InvalidOperationException("This path node is not a dict");

        public IMutableArray Array => field ?? throw new InvalidOperationException("This path node is not an array");

        public int ParentIndex => _parentIndex ?? throw new InvalidOperationException("Parent index not set");

        public string ParentKey => _parentKey ?? throw new InvalidOperationException("Parent key not set");

        private static PathNode CreateInternal(object? input)
        {
            return input switch
            {
                null => new PathNode(true),
                IMutableDictionary dict => new PathNode(dict),
                IMutableArray array => new PathNode(array),
                _ => new PathNode(false)
            };
        }

        public static PathNode Create(object? input, string parentKey)
        {
            var retVal = CreateInternal(input);
            retVal._parentKey = parentKey;
            return retVal;
        }

        public static PathNode Create(object? input, int parentIndex)
        {
            var retVal = CreateInternal(input);
            retVal._parentIndex = parentIndex;
            return retVal;
        }

        private PathNode(bool empty)
        {
            Type = empty ? PathNodeType.Missing : PathNodeType.Scalar;
        }

        public PathNode(IMutableDictionary dict)
        {
            Dict = dict;
            Type = PathNodeType.Dict;
        }

        private PathNode(IMutableArray array)
        {
            Array = array;
            Type = PathNodeType.Array;
        }
    }
}
