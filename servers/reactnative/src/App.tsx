// React Native UI for the Couchbase Lite Test Server.
// Provides device ID, WebSocket URL, Connect button, status display, and log output.
//
// Copyright 2025-Present Couchbase, Inc.
//
// Use of this software is governed by the Business Source License included
// in the file licenses/BSL-Couchbase.txt.  As of the Change Date specified
// in that file, in accordance with the Business Source License, use of this
// software will be governed by the Apache License, Version 2.0, included in
// the file licenses/APL2.txt.

import React, {useState, useRef, useCallback, useEffect} from 'react';
import {
  SafeAreaView,
  View,
  Text,
  TextInput,
  TouchableOpacity,
  ScrollView,
  StyleSheet,
  StatusBar,
  Platform,
} from 'react-native';
import {LaunchArguments} from 'react-native-launch-arguments';

import {TestServer, StateNames, TestServerState} from './testServer';
import {TDKImpl, APIVersion} from './tdk';
import {WebSocketState} from './webSocketClient';

interface AutoConnectParams {
  wsURL?: string;
  deviceID?: string;
}

const MAX_LOG_LINES = 200;
const AUTO_CONNECT_DELAY_MS = 1000;
const AUTO_CONNECT_RETRY_INTERVAL_MS = 2000;
const MAX_AUTO_CONNECT_RETRIES = 30;

const App: React.FC = () => {
  const [deviceID, setDeviceID] = useState('ws0');
  const [wsURL, setWsURL] = useState('ws://');
  const [status, setStatus] = useState('Disconnected');
  const [isConnected, setIsConnected] = useState(false);
  const [isConnecting, setIsConnecting] = useState(false);
  const [logs, setLogs] = useState<string[]>([]);

  const serverRef = useRef<TestServer | null>(null);
  const tdkRef = useRef<TDKImpl | null>(null);
  const scrollRef = useRef<ScrollView>(null);
  const autoConnectRef = useRef<{
    id: string;
    url: string;
    retryCount: number;
  } | null>(null);
  const autoConnectInitRef = useRef(false);

  const addLog = useCallback((message: string) => {
    const timestamp = new Date().toLocaleTimeString();
    setLogs(prev => {
      const next = [...prev, `[${timestamp}] ${message}`];
      if (next.length > MAX_LOG_LINES) {
        return next.slice(next.length - MAX_LOG_LINES);
      }
      return next;
    });
  }, []);

  const connectToServer = useCallback(
    (id: string, url: string) => {
      if (!id.trim() || !url.trim()) {
        addLog('ERROR: Please fill in device ID and WebSocket URL');
        return;
      }

      if (serverRef.current) {
        serverRef.current.close();
        serverRef.current = null;
      }
      if (tdkRef.current) {
        tdkRef.current.dispose();
        tdkRef.current = null;
      }

      setIsConnecting(true);
      setStatus('Connecting...');
      addLog(`Connecting to ${url} as device ${id}...`);

      const tdk = new TDKImpl();
      tdk.onLog = addLog;
      tdkRef.current = tdk;

      const server = new TestServer(id.trim(), APIVersion);
      server.onLog = addLog;
      server.delegate = tdk;

      server.onStateChange = (state: WebSocketState) => {
        if (serverRef.current !== server) {
          return;
        }

        const stateName = StateNames[state] ?? 'unknown';
        setStatus(server.error ?? stateName);
        addLog(`Connection state: ${stateName}`);

        if (state === WebSocketState.Open) {
          setIsConnected(true);
          setIsConnecting(false);
          if (autoConnectRef.current) {
            autoConnectRef.current.retryCount = 0;
          }
        } else if (
          state === WebSocketState.Closed ||
          state === WebSocketState.Closing
        ) {
          setIsConnected(false);
          setIsConnecting(false);
          if (server.error) {
            addLog(`Error: ${server.error}`);
          }

          const ac = autoConnectRef.current;
          if (ac && state === WebSocketState.Closed) {
            ac.retryCount++;
            if (ac.retryCount <= MAX_AUTO_CONNECT_RETRIES) {
              const delaySec = AUTO_CONNECT_RETRY_INTERVAL_MS / 1000;
              addLog(
                `Auto-reconnect in ${delaySec}s (attempt ${ac.retryCount}/${MAX_AUTO_CONNECT_RETRIES})...`,
              );
              setStatus(`Retrying (${ac.retryCount}/${MAX_AUTO_CONNECT_RETRIES})...`);
              setTimeout(
                () => connectToServer(ac.id, ac.url),
                AUTO_CONNECT_RETRY_INTERVAL_MS,
              );
            } else {
              addLog('Auto-connect failed: max retries exceeded');
              setStatus('Auto-connect failed');
            }
          }
        }
      };

      serverRef.current = server;
      server.connect(url.trim());
    },
    [addLog],
  );

  const handleConnect = useCallback(() => {
    connectToServer(deviceID, wsURL);
  }, [deviceID, wsURL, connectToServer]);

  useEffect(() => {
    if (autoConnectInitRef.current) {
      return;
    }
    try {
      const args = LaunchArguments.value<AutoConnectParams>();
      if (args.wsURL && args.deviceID) {
        autoConnectInitRef.current = true;
        autoConnectRef.current = {
          id: args.deviceID,
          url: args.wsURL,
          retryCount: 0,
        };
        addLog(
          `Auto-connect from launch args: device=${args.deviceID} url=${args.wsURL}`,
        );
        setDeviceID(args.deviceID);
        setWsURL(args.wsURL);
        const {deviceID: id, wsURL: url} = args;
        setTimeout(() => connectToServer(id, url), AUTO_CONNECT_DELAY_MS);
      }
    } catch (_e) {
      // Launch arguments not available — stay in manual mode
    }
  }, [addLog, connectToServer]);

  const handleDisconnect = useCallback(() => {
    autoConnectRef.current = null;
    if (serverRef.current) {
      serverRef.current.close();
      serverRef.current = null;
    }
    if (tdkRef.current) {
      tdkRef.current.dispose();
      tdkRef.current = null;
    }
    setIsConnected(false);
    setIsConnecting(false);
    setStatus('Disconnected');
    addLog('Disconnected');
  }, [addLog]);

  const handleClearLogs = useCallback(() => {
    setLogs([]);
  }, []);

  return (
    <SafeAreaView style={styles.container}>
      <StatusBar barStyle="light-content" backgroundColor="#1a1a2e" />
      <View style={styles.header}>
        <Text style={styles.title}>CBL Test Server</Text>
        <Text style={styles.subtitle}>
          React Native | {Platform.OS} {Platform.Version}
        </Text>
      </View>

      <View style={styles.form}>
        <View style={styles.inputRow}>
          <Text style={styles.label}>Device ID:</Text>
          <TextInput
            style={styles.input}
            value={deviceID}
            onChangeText={setDeviceID}
            placeholder="ws0"
            placeholderTextColor="#666"
            editable={!isConnected && !isConnecting}
            autoCapitalize="none"
            autoCorrect={false}
          />
        </View>

        <View style={styles.inputRow}>
          <Text style={styles.label}>WS URL:</Text>
          <TextInput
            style={styles.input}
            value={wsURL}
            onChangeText={setWsURL}
            placeholder="ws://10.0.0.5:8765"
            placeholderTextColor="#666"
            editable={!isConnected && !isConnecting}
            autoCapitalize="none"
            autoCorrect={false}
            keyboardType="url"
          />
        </View>

        <View style={styles.buttonRow}>
          {!isConnected ? (
            <TouchableOpacity
              style={[
                styles.button,
                styles.connectButton,
                isConnecting && styles.buttonDisabled,
              ]}
              onPress={handleConnect}
              disabled={isConnecting}>
              <Text style={styles.buttonText}>
                {isConnecting ? 'Connecting...' : 'Connect'}
              </Text>
            </TouchableOpacity>
          ) : (
            <TouchableOpacity
              style={[styles.button, styles.disconnectButton]}
              onPress={handleDisconnect}>
              <Text style={styles.buttonText}>Disconnect</Text>
            </TouchableOpacity>
          )}
          <TouchableOpacity
            style={[styles.button, styles.clearButton]}
            onPress={handleClearLogs}>
            <Text style={styles.buttonText}>Clear Logs</Text>
          </TouchableOpacity>
        </View>
      </View>

      <View style={styles.statusBar}>
        <View
          style={[
            styles.statusDot,
            isConnected
              ? styles.statusDotConnected
              : isConnecting
                ? styles.statusDotConnecting
                : styles.statusDotDisconnected,
          ]}
        />
        <Text style={styles.statusText}>{status}</Text>
      </View>

      <View style={styles.logContainer}>
        <Text style={styles.logHeader}>Logs</Text>
        <ScrollView
          ref={scrollRef}
          style={styles.logScroll}
          onContentSizeChange={() =>
            scrollRef.current?.scrollToEnd({animated: false})
          }>
          {logs.map((line, i) => (
            <Text key={i} style={styles.logLine}>
              {line}
            </Text>
          ))}
          {logs.length === 0 && (
            <Text style={styles.logPlaceholder}>
              Logs will appear here when connected...
            </Text>
          )}
        </ScrollView>
      </View>
    </SafeAreaView>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#0f0f23',
  },
  header: {
    paddingHorizontal: 20,
    paddingTop: 16,
    paddingBottom: 12,
  },
  title: {
    fontSize: 24,
    fontWeight: '700',
    color: '#e0e0e0',
  },
  subtitle: {
    fontSize: 13,
    color: '#888',
    marginTop: 2,
  },
  form: {
    paddingHorizontal: 20,
    gap: 10,
  },
  inputRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
  },
  label: {
    color: '#aaa',
    fontSize: 14,
    width: 75,
  },
  input: {
    flex: 1,
    backgroundColor: '#1a1a2e',
    borderWidth: 1,
    borderColor: '#333',
    borderRadius: 8,
    paddingHorizontal: 12,
    paddingVertical: 10,
    color: '#e0e0e0',
    fontSize: 14,
  },
  buttonRow: {
    flexDirection: 'row',
    gap: 10,
    marginTop: 6,
  },
  button: {
    flex: 1,
    paddingVertical: 12,
    borderRadius: 8,
    alignItems: 'center',
  },
  connectButton: {
    backgroundColor: '#2d6a4f',
  },
  disconnectButton: {
    backgroundColor: '#9b2226',
  },
  clearButton: {
    backgroundColor: '#333',
  },
  buttonDisabled: {
    opacity: 0.5,
  },
  buttonText: {
    color: '#fff',
    fontSize: 15,
    fontWeight: '600',
  },
  statusBar: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 20,
    paddingVertical: 10,
    gap: 8,
  },
  statusDot: {
    width: 10,
    height: 10,
    borderRadius: 5,
  },
  statusDotConnected: {
    backgroundColor: '#40c057',
  },
  statusDotConnecting: {
    backgroundColor: '#fab005',
  },
  statusDotDisconnected: {
    backgroundColor: '#888',
  },
  statusText: {
    color: '#ccc',
    fontSize: 14,
  },
  logContainer: {
    flex: 1,
    marginHorizontal: 20,
    marginBottom: 16,
  },
  logHeader: {
    color: '#888',
    fontSize: 12,
    fontWeight: '600',
    textTransform: 'uppercase',
    letterSpacing: 1,
    marginBottom: 6,
  },
  logScroll: {
    flex: 1,
    backgroundColor: '#1a1a2e',
    borderRadius: 8,
    padding: 10,
  },
  logLine: {
    color: '#7ec8e3',
    fontSize: 11,
    fontFamily: Platform.OS === 'ios' ? 'Menlo' : 'monospace',
    lineHeight: 16,
  },
  logPlaceholder: {
    color: '#555',
    fontSize: 12,
    fontStyle: 'italic',
  },
});

export default App;
