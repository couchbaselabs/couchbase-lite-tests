#!/usr/bin/env node
/**
 * Patches cbl-reactnative's iOS ReplicatorHelper to include domain + code
 * in replicator status error JSON (matches the Android Kotlin patch).
 *
 * Without this, iOS reports replicator errors with only a message and the
 * Python TDK cannot assert on domain/code (e.g. test_replicate_non_existing_sg_collections).
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
  'ReplicatorHelper.swift',
);

if (!fs.existsSync(filePath)) {
  console.warn(
    '[patch-ios-replicator-status] ReplicatorHelper.swift not found — skipping',
  );
  process.exit(0);
}

const original = fs.readFileSync(filePath, 'utf8');

const originalBlock =
  '        if let error = status.error {\n' +
  '            errorJson = [\n' +
  '                "message": error.localizedDescription\n' +
  '            ]\n' +
  '        }';

const patchedBlock =
  '        if let error = status.error {\n' +
  '            let nsErr = error as NSError\n' +
  '            errorJson = [\n' +
  '                "domain": "CBL",\n' +
  '                "code": nsErr.code,\n' +
  '                "message": error.localizedDescription\n' +
  '            ]\n' +
  '        }';

if (original.includes('"code": nsErr.code')) {
  console.log('[patch-ios-replicator-status] Already patched');
  process.exit(0);
}

if (!original.includes(originalBlock)) {
  console.warn(
    '[patch-ios-replicator-status] Expected block not found — upstream may have changed',
  );
  process.exit(0);
}

fs.writeFileSync(
  filePath,
  original.replace(originalBlock, patchedBlock),
  'utf8',
);
console.log(
  '[patch-ios-replicator-status] Patched replicator status error JSON in ReplicatorHelper.swift',
);
