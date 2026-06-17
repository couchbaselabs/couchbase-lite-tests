#!/usr/bin/env node
/**
 * Patches cbl-reactnative's iOS LogSinksManager to route writeLog through NSLog.
 *
 * Xcode 26 / Swift 6: CouchbaseLiteSwift.Log.log is present in the binary but not
 * visible to the compiler in this pod target, which breaks the build. Routing via
 * NSLog keeps the TDK able to exercise the write-log API surface and lets the pod
 * compile. Isolated here so a future SDK fix is a one-line revert.
 */

const fs = require('fs');
const path = require('path');

const filePath = path.join(
  __dirname,
  '..',
  'node_modules',
  'cbl-reactnative',
  'cblite-js-common',
  'cbl-js-swift',
  'LogSinksManager.swift',
);

if (!fs.existsSync(filePath)) {
  console.warn(
    '[patch-ios-logsinks] LogSinksManager.swift not found — skipping',
  );
  process.exit(0);
}

const original = fs.readFileSync(filePath, 'utf8');

const originalLine =
  '        Log.log(domain: logDomain, level: logLevel, message: message)';

const patchedLine =
  '        // Xcode 26 / Swift 6: CouchbaseLiteSwift.Log.log is present in the\n' +
  '        // binary but not visible to the compiler in this pod target. Route via NSLog\n' +
  '        // so the TDK can still exercise the write-log API surface.\n' +
  '        NSLog("[CBL][%@][%d] %@", domain, level, message)';

if (original.includes('NSLog("[CBL][%@][%d] %@"')) {
  console.log('[patch-ios-logsinks] Already patched');
  process.exit(0);
}

if (!original.includes(originalLine)) {
  console.warn(
    '[patch-ios-logsinks] Expected line not found — upstream may have changed',
  );
  process.exit(0);
}

fs.writeFileSync(
  filePath,
  original.replace(originalLine, patchedLine),
  'utf8',
);
console.log(
  '[patch-ios-logsinks] Patched writeLog to use NSLog fallback in LogSinksManager.swift',
);
