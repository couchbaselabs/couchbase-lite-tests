#!/usr/bin/env node
/**
 * Patches cbl-reactnative's Android ReplicatorHelper to include domain + code
 * in replicator status error JSON (matches the iOS Swift patch).
 */

const fs = require('fs');
const path = require('path');

const filePath = path.join(
  __dirname,
  '..',
  'node_modules',
  'cbl-reactnative',
  'cblite-js-common',
  'cbl-js-kotlin',
  'ReplicatorHelper.kt',
);

if (!fs.existsSync(filePath)) {
  console.warn(
    '[patch-android-replicator-status] ReplicatorHelper.kt not found — skipping',
  );
  process.exit(0);
}

const original = fs.readFileSync(filePath, 'utf8');

const patchedBlock =
  '        // Process error if present\n' +
  '        if (status.error != null) {\n' +
  '            val errorMap = Arguments.createMap()\n' +
  '            val err = status.error\n' +
  '            if (err is CouchbaseLiteException) {\n' +
  '                errorMap.putString("domain", "CBL")\n' +
  '                errorMap.putInt("code", err.code)\n' +
  '            }\n' +
  '            errorMap.putString("message", err?.message)\n' +
  '            resultMap.putMap("error", errorMap)\n' +
  '        }';

const originalBlock =
  '        // Process error if present\n' +
  '        if (status.error != null) {\n' +
  '            val errorMap = Arguments.createMap()\n' +
  '            errorMap.putString("message", status.error?.message)\n' +
  '            resultMap.putMap("error", errorMap)\n' +
  '        }';

if (original.includes('errorMap.putInt("code", err.code)')) {
  console.log('[patch-android-replicator-status] Already patched');
  process.exit(0);
}

if (!original.includes(originalBlock)) {
  console.warn(
    '[patch-android-replicator-status] Expected block not found — upstream may have changed',
  );
  process.exit(0);
}

fs.writeFileSync(
  filePath,
  original.replace(originalBlock, patchedBlock),
  'utf8',
);
console.log(
  '[patch-android-replicator-status] Patched replicator status error JSON in ReplicatorHelper.kt',
);
