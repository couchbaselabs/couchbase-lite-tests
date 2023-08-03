using Couchbase.Lite;
using sly.buildresult;
using sly.lexer;
using System;
using System.Collections;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Threading.Tasks;

namespace TestServer.Utilities
{
    internal sealed class KeyPathTokenEnumerator : IEnumerator<Token<KeyPathToken>>
    {
        private readonly bool _reverse;
        private readonly Token<KeyPathToken> _original;

        public Token<KeyPathToken> Current { get; private set; }

        object IEnumerator.Current => Current;

        public KeyPathTokenEnumerator(Token<KeyPathToken> token, bool reverse)
        {
            Current = token;
            _reverse = reverse;
            _original = token;
        }

        public void Dispose()
        {
            // No-op
        }

        public bool MoveNext()
        {
            if(_reverse) {
                Current = Current.Previous(0);
            } else {
                Current = Current.Next(0);
            }

            return Current != null;
        }

        public void Reset()
        {
            Current = _original;
        }
    }

    internal sealed class KeyPathTokenEnumerable : IEnumerable<Token<KeyPathToken>>
    {
        private readonly Token<KeyPathToken> _token;
        private readonly bool _reverse;

        public KeyPathTokenEnumerable(Token<KeyPathToken> token, bool reverse)
        {
            _token = token;
            _reverse = reverse;
        }

        public IEnumerator<Token<KeyPathToken>> GetEnumerator() => new KeyPathTokenEnumerator(_token, _reverse);

        IEnumerator IEnumerable.GetEnumerator() => GetEnumerator();
    }

    internal sealed class KeyPathException : Exception
    {
        public KeyPathException(string prefix, Token<KeyPathToken> token)
            :base($"{prefix} {BadToken(token)}")
        {

        }

        private static string BadToken(Token<KeyPathToken> token)
        {
            if(token.TokenID == KeyPathToken.NONE) {
                if(token.Previous(0) == null) {
                    return "";
                }

                token = token.Previous(0);
            }

            var previous = new KeyPathTokenEnumerable(token, true);
            var next = new KeyPathTokenEnumerable(token, false);
            var numPrevious = previous.Count();
            var numNext = next.Count() - 1; // discard EOL token
            const int tokensToShow = 3;

            var sb = new StringBuilder($"at position {token.Position.Column} -> '");
            if (numPrevious > 0) {
                if (numPrevious > tokensToShow) {
                    sb.Append("... ");
                }

                foreach(var t in previous.Take(Math.Min(tokensToShow, numPrevious)).Reverse()) {
                    sb.Append(t.Value);
                }
            }

            sb.Append($" >{token.Value}< ");

            if (numNext > 0) {
                foreach (var t in next.Take(Math.Min(tokensToShow, numNext))) {
                    sb.Append(t.Value);
                }

                if (numNext > tokensToShow) {
                    sb.Append(" ...");
                }
            }

            sb.Append("'");
            return sb.ToString();
        }
    }

    internal enum KeyPathToken
    {
        NONE,

        [Lexeme("\\[")]
        OPEN_BRACKET,

        [Lexeme("\\]")]
        CLOSE_BRACKET,

        [Lexeme("\\-?[0-9]+")]
        INT,

        [Lexeme("\\.")]
        DOT,

        [Lexeme("\\\\")]
        BACKSLASH,

        [Lexeme("[^\\\\\\]\\[\\.]+")]
        IDENTIFIER
    }

    internal static class KeyPathParser
    {
        private static readonly ILexer<KeyPathToken> _lexer;

        static KeyPathParser()
        {
            var buildResult = LexerBuilder.BuildLexer(new BuildResult<ILexer<KeyPathToken>>());
            if(buildResult.IsError) {
                throw new ApplicationException("KeyPathParser failed to build");
            }

            _lexer = buildResult.Result;
        }

        private static IEnumerable<Token<KeyPathToken>> Lex(string keypath)
        {
            var tokenizeResult = _lexer.Tokenize(keypath);
            if (tokenizeResult.IsError) {
                throw new ApplicationException($"Failed to lex keypath '{keypath}'");
            }

            return tokenizeResult.Tokens;
        }

        

        private static void CheckBracket(bool actual, bool expected, Token<KeyPathToken> token)
        {
            if(actual != expected) {
                throw new KeyPathException("Invalid bracket in keypath", token);
            }
        }

        private static PathNode BackfillArrayIfNeeded(Stack<PathNode> pathStack, PathNode current)
        {
            if(current.Type != PathNodeType.Missing) {
                return current;
            }

            var backfill = new MutableArrayObject();
            pathStack.Pop();
            var parent = pathStack.Peek();
            if (parent.Type == PathNodeType.Dict) {
                parent.Dict.SetArray(current.ParentKey, backfill);
                current = PathNode.Create(backfill, current.ParentKey);
            } else {
                parent.Array.SetArray(current.ParentIndex, backfill);
                current = PathNode.Create(backfill, current.ParentIndex);
            }

            pathStack.Push(current);
            return current;
        }

        private static PathNode BackfillDictIfNeeded(Stack<PathNode> pathStack, PathNode current)
        {
            if (current.Type != PathNodeType.Missing) {
                return current;
            }

            var backfill = new MutableDictionaryObject();
            pathStack.Pop();
            var parent = pathStack.Peek();
            if (parent.Type == PathNodeType.Dict) {
                parent.Dict.SetDictionary(current.ParentKey, backfill);
                current = PathNode.Create(backfill, current.ParentKey);
            } else {
                parent.Array.SetDictionary(current.ParentIndex, backfill);
                current = PathNode.Create(backfill, current.ParentIndex);
            }

            pathStack.Push(current);
            return current;
        }


        public static void Update(IMutableDictionary source, string keypath, object value)
        {
            var pathStack = new Stack<PathNode>();
            pathStack.Push(new PathNode(source));
            var inBracket = false;
            var currentKey = "";
            var currentIndex = -1;
            foreach (var token in Lex(keypath)) {
                switch (token.TokenID) {
                    case KeyPathToken.CLOSE_BRACKET: {
                        // If it is escaped, it is part of the dictionary key, so append it
                        if (token.Previous(0).TokenID == KeyPathToken.BACKSLASH) {
                            currentKey += "]";
                            break;
                        }

                        CheckBracket(inBracket, true, token);
                        if(token.Previous(0).TokenID != KeyPathToken.INT) {
                            // Close bracket can only come after backslash (handled above) or int
                            throw new KeyPathException("Invalid closing bracket in keypath", token);
                        }

                        inBracket = false;
                        var current = pathStack.Peek();
                        if (current.Type != PathNodeType.Array && current.Type != PathNodeType.Missing) {
                            // When the actual object was examined, a non-array was found so we cannot proceed
                            throw new KeyPathException("Non-array found when array requested by keypath", token);
                        }

                        current = BackfillArrayIfNeeded(pathStack, current);
                        var array = current.Array;
                        while (array.Count <= currentIndex) {
                            array.AddValue(null);
                        }

                        var nextNode = PathNode.Create(array.GetValue(currentIndex), currentIndex);
                        if (nextNode.Type == PathNodeType.Scalar) {
                            // This array contains a scalar at the requested position, but the keypath is not terminated yet
                            throw new KeyPathException($"Scalar found inside of array at position {currentIndex}", token);
                        }

                        currentIndex = -1;
                        pathStack.Push(nextNode);
                        break;
                    }
                    case KeyPathToken.BACKSLASH:
                        if (inBracket) {
                            throw new KeyPathException("Invalid KeyPath (backslash inside brackets)", token);
                        }

                        break;
                    case KeyPathToken.INT: {
                        if (!inBracket) {
                            throw new KeyPathException("Invalid KeyPath (raw int outside of bracket)", token);
                        }

                        if(token.IntValue < 0) {
                            throw new KeyPathException("Invalid KeyPath (negative array index)", token);
                        }

                        currentIndex = token.IntValue;
                        break;
                    }
                    case KeyPathToken.OPEN_BRACKET:
                    case KeyPathToken.DOT: {
                        // If it is escaped, it is part of the dictionary key, so append it
                        if (token.Previous(0).TokenID == KeyPathToken.BACKSLASH) {
                            currentKey += token.TokenID == KeyPathToken.DOT ? "." : "[";
                            break;
                        }

                        if(token.Previous(0).TokenID != KeyPathToken.IDENTIFIER) {
                            throw new KeyPathException("Invalid keypath component", token);
                        }

                        if(token.TokenID == KeyPathToken.OPEN_BRACKET) {
                            CheckBracket(inBracket, false, token);
                            inBracket = true;
                        }

                        var current = pathStack.Peek();
                        if (current.Type != PathNodeType.Dict && current.Type != PathNodeType.Missing) {
                            // A dictionary was requested but the found entry for this path was an array or a scalar, cannot proceed
                            throw new KeyPathException("Non-dictionary found when dictionary requested by keypath", token);
                        }

                        current = BackfillDictIfNeeded(pathStack, current);
                        var dict = current.Dict;
                        var nextNode = PathNode.Create(dict.GetValue(currentKey), currentKey);
                        if (nextNode.Type == PathNodeType.Scalar) {
                            // This dictionary contains a scalar at the requested key, but the keypath is not terminated yet
                            throw new KeyPathException($"Scalar found inside of dictionary for key '{currentKey}'", token);
                        }

                        pathStack.Push(nextNode);
                        currentKey = "";
                        break;
                    }
                    case KeyPathToken.IDENTIFIER:
                        if(currentKey.Length == 0 && token.Previous(0)?.TokenID == KeyPathToken.OPEN_BRACKET) {
                            throw new KeyPathException("Non-integer found inside of index brackets", token);
                        }

                        currentKey += token.StringWithoutQuotes;
                        break;
                    case KeyPathToken.NONE: {
                        // This comes as the final token
                        if(token.Previous(0) == null) {
                            throw new KeyPathException("Empty keypath", token);
                        }

                        var current = pathStack.Peek();
                        if(currentKey.Length > 0) {
                            // This needs to be finished now since there is no final dot
                            current = BackfillDictIfNeeded(pathStack, current);
                        } else if(current.Type == PathNodeType.Missing || current.Type == PathNodeType.Array) {
                            // Because arrays always have an explicit termination character, 
                            // the complete information is always on the stack.  Unwind it
                            // a bit so the next logic can be consistent with dict
                            currentIndex = current.ParentIndex;
                            pathStack.Pop();
                            current = pathStack.Peek();
                        } else {
                            throw new ApplicationException("Ended up in an uncertain state about whether the end of the keypath is a dict or array");
                        }
                      
                        if (current.Type == PathNodeType.Dict) {
                            if(currentKey.Length == 0) {
                                // We ended up with an index, but found a dict in the tree
                                throw new KeyPathException("Keypath ends in an array index but data doesn't contain an array", token);
                            }

                            var dict = current.Dict;
                            dict.SetValue(currentKey, value.ToDocumentObject());
                        } else {
                            if(currentIndex == -1) {
                                // We ended up with a key, but found an array in the tree
                                throw new KeyPathException("Keypath ends in a key but data doesn't contain a dictionary", token);
                            }

                            var array = current.Array;
                            array.SetValue(currentIndex, value.ToDocumentObject());
                        }
                        break;
                    }
                    default:
                        throw new KeyPathException("Invalid character", token);
                }
            }
        }

        public static void Remove(IMutableDictionary source, string keypath)
        {
            var pathStack = new Stack<PathNode>();
            pathStack.Push(new PathNode(source));
            var inBracket = false;
            var currentKey = "";
            var currentIndex = -1;
            foreach(var token in Lex(keypath)) {
                switch(token.TokenID) {
                    case KeyPathToken.OPEN_BRACKET:
                        if(token.Previous(0).TokenID == KeyPathToken.BACKSLASH) {
                            currentKey += "[";
                            break;
                        }

                        CheckBracket(inBracket, false, token);
                        inBracket = true;
                        break;
                    case KeyPathToken.CLOSE_BRACKET: {
                        // If it is escaped, it is part of the dictionary key, so append it
                        if (token.Previous(0).TokenID == KeyPathToken.BACKSLASH) {
                            currentKey += "]";
                            break;
                        }

                        CheckBracket(inBracket, true, token);
                        inBracket = false;
                        var current = pathStack.Peek();
                        if (current.Type != PathNodeType.Array) {
                            // Asked to remove an array index on a non-array, already doesn't exist
                            return;
                        }

                        var array = current.Array;
                        if (currentIndex < 0 || currentIndex >= array.Count) {
                            // Nonsense index, nothing to do
                            return;
                        }

                        var nextNode = PathNode.Create(array.GetValue(currentIndex), currentIndex);
                        if (nextNode.Type == PathNodeType.Scalar || nextNode.Type == PathNodeType.Missing) {
                            // This path does not contain a container
                            return;
                        }

                        currentIndex = -1;
                        pathStack.Push(nextNode);
                        break;
                    }
                    case KeyPathToken.BACKSLASH:
                        if (inBracket) {
                            throw new KeyPathException("Invalid KeyPath (backslash inside brackets)", token);
                        }

                        break;
                    case KeyPathToken.INT: {
                        if (!inBracket) {
                            throw new KeyPathException("Invalid KeyPath (raw int outside of bracket)", token);
                        }

                        currentIndex = token.IntValue;
                        break;
                    } 
                    case KeyPathToken.DOT: {
                        // If it is escaped, it is part of the dictionary key, so append it
                        if (token.Previous(0).TokenID == KeyPathToken.BACKSLASH) {
                            currentKey += ".";
                            break;
                        }

                        var current = pathStack.Peek();
                        if (current.Type != PathNodeType.Dict) {
                            // Asked to remove a key on a non-dictionary, already doesn't exist
                            return;
                        }

                        var dict = current.Dict;
                        var nextNode = PathNode.Create(dict.GetValue(currentKey), currentKey);
                        if (nextNode.Type == PathNodeType.Scalar || nextNode.Type == PathNodeType.Missing) {
                            // This path does not contain a container
                            return;
                        }

                        currentKey = "";
                        pathStack.Push(nextNode);
                        break;
                    }
                    case KeyPathToken.IDENTIFIER:
                        currentKey += token.StringWithoutQuotes;
                        break;
                    case KeyPathToken.NONE: {
                        // This comes as the final token
                        var current = pathStack.Peek();
                        if (current.Type == PathNodeType.Dict) {
                            var dict = current.Dict;
                            dict.Remove(currentKey);
                        } else if(current.Type == PathNodeType.Array) {
                            var array = current.Array;
                            array.RemoveAt(currentIndex);
                        }
                        break;
                    }
                }
            }
        }
    }
}
