﻿namespace TestServer
{
    internal sealed class AutoReaderWriterLock : IDisposable
    {
        private readonly ReaderWriterLockSlim _lock = new ReaderWriterLockSlim();

        public interface IUpgradeableLockImpl : IDisposable
        {
            void Upgrade();
        }

        private abstract class Impl : IDisposable
        {
            private readonly ReaderWriterLockSlim _lock;

            protected Impl(ReaderWriterLockSlim l)
            {
                _lock = l;
                EnterLock(l);
            }

            protected abstract void ExitLock(ReaderWriterLockSlim l);

            protected abstract void EnterLock(ReaderWriterLockSlim l);

            public void Upgrade()
            {
                _lock.EnterWriteLock();
            }

            public void Dispose()
            {
                ExitLock(_lock);
            }
        }

        private sealed class ImplReader : Impl
        {
            public ImplReader(ReaderWriterLockSlim l) : base(l)
            {
            }

            protected override void ExitLock(ReaderWriterLockSlim l)
            {
                l.ExitReadLock();
            }

            protected override void EnterLock(ReaderWriterLockSlim l)
            {
                l.EnterReadLock();
            }
        }

        private sealed class ImplUpgradeableReader : Impl, IUpgradeableLockImpl
        {
            public ImplUpgradeableReader(ReaderWriterLockSlim l) : base(l)
            {
            }

            protected override void ExitLock(ReaderWriterLockSlim l)
            {
                l.ExitUpgradeableReadLock();
            }

            protected override void EnterLock(ReaderWriterLockSlim l)
            {
                l.EnterUpgradeableReadLock();
            }
        }

        private sealed class ImplWriter : Impl
        {
            public ImplWriter(ReaderWriterLockSlim l) : base(l)
            {
            }

            protected override void ExitLock(ReaderWriterLockSlim l)
            {
                l.ExitWriteLock();
            }

            protected override void EnterLock(ReaderWriterLockSlim l)
            {
                l.EnterWriteLock();
            }
        }

        public IDisposable GetReadLock() => new ImplReader(_lock);

        public IUpgradeableLockImpl GetUpgradeableReadLock() => new ImplUpgradeableReader(_lock);

        public IDisposable GetWriteLock() => new ImplWriter(_lock);

        public void Dispose()
        {
            _lock.Dispose();
        }
    }
}
