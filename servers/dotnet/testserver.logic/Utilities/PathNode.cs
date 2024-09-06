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
        private readonly IMutableDictionary? _dict;
        private readonly IMutableArray? _array;
        private int? _parentIndex;
        private string? _parentKey;

        public PathNodeType Type { get; }

        public IMutableDictionary Dict => _dict ?? throw new InvalidOperationException("This path node is not a dict");

        public IMutableArray Array => _array ?? throw new InvalidOperationException("This path node is not an array");

        public int ParentIndex => _parentIndex.HasValue ? _parentIndex.Value : throw new InvalidOperationException("Parent index not set");

        public string ParentKey => _parentKey ?? throw new InvalidOperationException("Parent key not set");

        private static PathNode CreateInternal(object? input)
        {
            if (input == null) {
                return new PathNode(true);
            }

            if (input is IMutableDictionary dict) {
                return new PathNode(dict);
            }

            if (input is IMutableArray array) {
                return new PathNode(array);
            }

            return new PathNode(false);
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

        public PathNode(bool empty)
        {
            Type = empty ? PathNodeType.Missing : PathNodeType.Scalar;
        }

        public PathNode(IMutableDictionary dict)
        {
            _dict = dict;
            Type = PathNodeType.Dict;
        }

        public PathNode(IMutableArray array)
        {
            _array = array;
            Type = PathNodeType.Array;
        }
    }
}
