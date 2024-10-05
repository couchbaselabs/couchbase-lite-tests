//
//  CertUtil.swift
//  TestServer
//
//  Created by Pasin Suriyentrakorn on 10/3/24.
//

import Foundation

struct CertUtil {
    static func certificate(from pem: String) -> SecCertificate? {
        // Remove the PEM header and footer
        let certBase64 = pem
            .replacingOccurrences(of: "-----BEGIN CERTIFICATE-----", with: "")
            .replacingOccurrences(of: "-----END CERTIFICATE-----", with: "")
            .replacingOccurrences(of: "\n", with: "")
        
        // Decode the base64 string into Data
        guard let data = Data(base64Encoded: certBase64) else {
            return nil
        }
        
        // Create a SecCertificate from the DER-encoded data
        guard let certificate = SecCertificateCreateWithData(nil, data as CFData) else {
            return nil
        }
        
        return certificate
    }
}
