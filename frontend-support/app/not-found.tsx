export default function NotFound() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center p-8">
      <div className="max-w-md rounded-xl border border-[var(--line)] bg-[var(--panel-solid)] p-6 text-center">
        <h2 className="mb-3 text-lg font-semibold">Page Not Found</h2>
        <p className="mb-4 text-sm text-[var(--muted)]">
          The page you are looking for does not exist.
        </p>
        <a
          href="/"
          className="btn btn-primary inline-block px-4 py-2 text-sm"
        >
          Go to Home
        </a>
      </div>
    </div>
  );
}