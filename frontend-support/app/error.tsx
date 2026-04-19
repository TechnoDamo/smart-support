'use client';

import { useEffect } from 'react';

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <div className="flex min-h-screen flex-col items-center justify-center p-8">
      <div className="max-w-md rounded-xl border border-[var(--line)] bg-[var(--panel-solid)] p-6 text-center">
        <h2 className="mb-3 text-lg font-semibold">Something went wrong!</h2>
        <p className="mb-4 text-sm text-[var(--muted)]">
          {error.message || 'An unexpected error occurred'}
        </p>
        <button
          className="btn btn-primary px-4 py-2 text-sm"
          onClick={() => reset()}
        >
          Try again
        </button>
      </div>
    </div>
  );
}