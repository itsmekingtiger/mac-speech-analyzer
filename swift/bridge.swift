import Foundation

// Async compat
final class ResultBox<T>: @unchecked Sendable {
    var value: Result<T, Error>?
}

func runBlocking<T: Sendable>(_ body: @Sendable @escaping () async throws -> T) throws -> T {
    let box = ResultBox<T>()
    let semaphore = DispatchSemaphore(value: 0)
    Task.detached {
        do    { box.value = .success(try await body()) }
        catch { box.value = .failure(error) }
        semaphore.signal()
    }
    semaphore.wait()
    return try box.value!.get()
}

// New symbol because the request-scoped callback changes the C ABI.
@_cdecl("msa_transcribe_v2")
public func msaTranscribe(
                        _ url: UnsafePointer<CChar>?,
                        _ locale: UnsafePointer<CChar>?,
                        _ outText: UnsafeMutablePointer<UnsafeMutablePointer<CChar>?>?,
                        _ outError: UnsafeMutablePointer<UnsafeMutablePointer<CChar>?>?,
                        _ onSegment: MSALiveTranscription?) -> Int32 {
    msaTranscribeV3(url, locale, outText, outError, onSegment, 0)
}

// Preserve the v2 ABI for existing callers; v3 optionally returns JSON.
@_cdecl("msa_transcribe_v3")
public func msaTranscribeV3(
                        _ url: UnsafePointer<CChar>?,
                        _ locale: UnsafePointer<CChar>?,
                        _ outText: UnsafeMutablePointer<UnsafeMutablePointer<CChar>?>?,
                        _ outError: UnsafeMutablePointer<UnsafeMutablePointer<CChar>?>?,
                        _ onSegment: MSALiveTranscription?,
                        _ timestamps: Int32) -> Int32 {
    let localeStr = locale.map { String(cString: $0) }   // nil stays nil
    let urlStr = url.map { String(cString: $0) }!
    do {
        let result = try runBlocking {
            try await transcribe(url: urlStr, locale: localeStr, timestamps: timestamps != 0, onSegment: { piece in
                if let onSegment { piece.withCString { onSegment($0) } }
            })
        }
        let text: String
        if timestamps != 0 {
            text = String(decoding: try JSONEncoder().encode(result), as: UTF8.self)
        } else {
            text = result.text
        }
        outText?.pointee = strdup(text)
        return 0
    } catch {
        outError?.pointee = strdup("\(error)")
        return 1
    }
}

@_cdecl("msa_free_string")
public func msaFreeString(_ ptr: UnsafeMutablePointer<CChar>?) {
    free(ptr)
}

public typealias MSALogCallback = @convention(c) (Int32, UnsafePointer<CChar>?) -> Void
private var logSink: MSALogCallback?

@_cdecl("msa_set_log_callback")
public func msa_set_log_callback(_ cb: MSALogCallback?) {
    logSink = cb
}

// use this everywhere instead of print()
func msaLog(_ level: Int32, _ message: String) {
    if let sink = logSink {
        message.withCString { sink(level, $0) }
    } else {
        print(message)          // fallback when nobody registered
    }
}

public typealias MSALiveTranscription = @convention(c) (UnsafePointer<CChar>?) -> Void
