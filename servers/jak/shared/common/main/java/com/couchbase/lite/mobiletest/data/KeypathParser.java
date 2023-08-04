//
// Copyright (c) 2023 Couchbase, Inc All rights reserved.
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
// http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.
//
package com.couchbase.lite.mobiletest.data;

import androidx.annotation.NonNull;

import com.couchbase.lite.mobiletest.errors.ClientError;
import com.couchbase.lite.mobiletest.util.Log;


/**
 * Grammar:
 * <p>
 * <p>keypath  ::= ( [ DOLLAR DOT ] &lt;property> | &lt;index> ) &lt;path>
 * <p>
 * <p>path     ::= ( DOT &lt;property> | &lt;index> )* EOP
 * <p>
 * <p>index    ::= OBRACKET DIGIT+ CBRACKET
 * <p>
 * <p>property ::= ANY+
 * <p>
 * <p>EOP      ::= End of path
 * <p>DOT      ::= '.'
 * <p>DOLLAR   ::= '$'
 * <p>OBRACKET ::= '['
 * <p>CBRACKET ::= ']'
 * <p>DIGIT    ::=  '0' |'1' | '2' | '3' | '4' | '5' | '6' | '7' | '8' | '9'
 * <p>ANY      ::= (! ( DOT | OBRACKET | CBRACKET | EOP ) ) | ESCAPE
 * <p>ESCAPE   ::= '\' (! EOP )
 */
public class KeypathParser {
    private enum CharClass {EOP, DOT, OBRACKET, CBRACKET, DOLLAR, DIGIT, ANY}

    private String keyPath;
    private int pathLen;

    private int curChPtr;
    private String curChar;
    private CharClass curCharClass;

    // definitely not thread safe...
    @NonNull
    public KeyPath parse(@NonNull String keyPath) {
        this.keyPath = keyPath;
        this.pathLen = keyPath.length();
        this.curChPtr = -1;

        final KeyPath parsedPath = new KeyPath();

        parseKeypath(parsedPath);

        return parsedPath;
    }

    @SuppressWarnings({"FallThrough", "PMD.MissingBreakInSwitch"})
    private void parseKeypath(@NonNull KeyPath parsedPath) {
        nextChar();
        switch (curCharClass) {
            case EOP:
                throw new ClientError("Empty path");
            case DOT:
            case CBRACKET:
                throw new ClientError("Unexpected character: " + curChar);
            case OBRACKET:
                nextChar();
                parseIndex(parsedPath);
                break;
            case DOLLAR:
                nextChar();
                if (curCharClass != CharClass.DOT) { throw new ClientError("Expecting a '.'"); }
                nextChar();
            default:
                parseProperty(parsedPath);
        }

        parsePath(parsedPath);
        if (parsedPath.size() < 1) { throw new ClientError(syntaxError("Empty keypath")); }
    }

    public void parsePath(@NonNull KeyPath parsedPath) {
        while (curCharClass != CharClass.EOP) {
            switch (curCharClass) {
                case DOT:
                    nextChar();
                    parseProperty(parsedPath);
                    break;
                case OBRACKET:
                    nextChar();
                    parseIndex(parsedPath);
                    break;
                default:
                    throw new ClientError(syntaxError("Unexpected character " + curChar));
            }
        }
    }

    private void parseProperty(@NonNull KeyPath parsedPath) {
        final StringBuilder prop = new StringBuilder();
        while ((curCharClass == CharClass.DOLLAR)
            || (curCharClass == CharClass.DIGIT)
            || (curCharClass == CharClass.ANY)) {
            prop.append(curChar);
            nextChar();
        }

        if (prop.length() < 1) { throw new ClientError(syntaxError("Empty property")); }
        parsedPath.addElement(new KeyPath.PathElem.Property(prop.toString()));
    }

    private void parseIndex(@NonNull KeyPath parsedPath) {
        final StringBuilder idx = new StringBuilder();
        while (curCharClass == CharClass.DIGIT) {
            idx.append(curChar);
            nextChar();
        }

        if (curCharClass != CharClass.CBRACKET) { throw new ClientError("Expecting a ']'"); }

        nextChar();

        if (idx.length() < 1) { throw new ClientError("Empty index"); }

        final int i;
        try { i = Integer.parseInt(idx.toString()); }
        catch (NumberFormatException e) { throw new ClientError(syntaxError("Unparsable index " + idx), e); }

        if (i < 0) { throw new ClientError(syntaxError("Negative index " + i)); }

        parsedPath.addElement(new KeyPath.PathElem.Index(i));
    }

    private void nextChar() {
        nextCh();
        switch (curChar) {
            case "":
                curCharClass = CharClass.EOP;
                return;
            case ".":
                curCharClass = CharClass.DOT;
                return;
            case "$":
                curCharClass = CharClass.DOLLAR;
                return;
            case "[":
                curCharClass = CharClass.OBRACKET;
                return;
            case "]":
                curCharClass = CharClass.CBRACKET;
                return;
            case "0":
            case "1":
            case "2":
            case "3":
            case "4":
            case "5":
            case "6":
            case "7":
            case "8":
            case "9":
                curCharClass = CharClass.DIGIT;
                return;
            case "\\":
                nextCh();
                if ("".equals(curChar)) { throw new ClientError(syntaxError("Dangling escape ('\\')")); }
                curCharClass = CharClass.ANY;
                return;
            default:
                curCharClass = CharClass.ANY;
        }
    }

    private void nextCh() {
        curChPtr++;
        curChar = (curChPtr >= pathLen) ? "" : keyPath.substring(curChPtr, curChPtr + 1);
    }

    @NonNull
    private String syntaxError(@NonNull String message) {
        return message + " at position " + curChPtr + " in keypath \"" + keyPath + "\"";
    }
}
