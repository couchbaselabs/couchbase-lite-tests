#!/usr/bin/env node
/**
 * Patches cbl-reactnative's Android bridge to implement pinnedServerCertificate.
 *
 * The upstream library leaves the Android certificate-pinning code as a TODO
 * comment. Without this patch, replicators connecting to Sync Gateway over TLS
 * fail with error 5008 (TLSCertUnknownRoot) because the device's system trust
 * store doesn't know the internal test CA.
 *
 * This script is run automatically by the "postinstall" npm hook so that the
 * fix survives every `npm install`.
 */

const fs = require('fs');
const path = require('path');

const filePath = path.join(
  __dirname,
  '..',
  'node_modules',
  'cbl-reactnative',
  'android',
  'src',
  'main',
  'java',
  'com',
  'cblreactnative',
  'cbl-js-kotlin',
  'ReplicatorHelper.kt',
);

if (!fs.existsSync(filePath)) {
  console.warn(
    '[patch-android-cert-pinning] ReplicatorHelper.kt not found — skipping patch',
  );
  process.exit(0);
}

const original = fs.readFileSync(filePath, 'utf8');

const TODO_COMMENT =
  '                    // Android doesn\'t support pinned certificates the same way as iOS\n' +
  '                    // This would need to be implemented using TrustManager if required';

const IMPLEMENTATION =
  '                    val certBytes = android.util.Base64.decode(certString, android.util.Base64.DEFAULT)\n' +
  '                    val certFactory = java.security.cert.CertificateFactory.getInstance("X.509")\n' +
  '                    val cert = certFactory.generateCertificate(\n' +
  '                        java.io.ByteArrayInputStream(certBytes)\n' +
  '                    ) as java.security.cert.X509Certificate\n' +
  '                    replicatorConfig.pinnedServerX509Certificate = cert';

if (original.includes(IMPLEMENTATION)) {
  console.log('[patch-android-cert-pinning] Already patched — nothing to do');
  process.exit(0);
}

if (!original.includes(TODO_COMMENT)) {
  console.warn(
    '[patch-android-cert-pinning] Expected TODO comment not found — the upstream package may have changed. Skipping patch.',
  );
  process.exit(0);
}

const patched = original.replace(TODO_COMMENT, IMPLEMENTATION);
fs.writeFileSync(filePath, patched, 'utf8');
console.log(
  '[patch-android-cert-pinning] Successfully patched pinnedServerCertificate in ReplicatorHelper.kt',
);
