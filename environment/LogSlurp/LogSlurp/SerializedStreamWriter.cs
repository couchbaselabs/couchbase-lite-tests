

namespace LogSlurp
{
    public sealed class SerializedStreamWriter : IDisposable, IAsyncDisposable
    {
        private readonly SemaphoreSlim _semaphore = new(1);
        private readonly StreamWriter _innerWriter;

        public SerializedStreamWriter(Stream stream)
        {
            _innerWriter = new StreamWriter(stream);
        }

        public void Dispose()
        {
            _semaphore.Wait();
            _innerWriter.Dispose();
            _semaphore.Dispose();
        }

        public async ValueTask DisposeAsync()
        {
            await _semaphore.WaitAsync().ConfigureAwait(false);
            await _innerWriter.DisposeAsync().ConfigureAwait(false);
            _semaphore.Dispose();
        }

        public async Task FlushAsync()
        {
            await _semaphore.WaitAsync().ConfigureAwait(false);
            try {
                await _innerWriter.FlushAsync().ConfigureAwait(false);
            } finally {
                _semaphore.Release();
            }
        }

        public async Task WriteAsync(string prologue, char[] line)
        {
            await _semaphore.WaitAsync().ConfigureAwait(false);
            try {
                await _innerWriter.WriteAsync(prologue).ConfigureAwait(false);
                await _innerWriter.WriteLineAsync(line).ConfigureAwait(false);
            } finally {
                _semaphore.Release();
            }
        }
    }
}
