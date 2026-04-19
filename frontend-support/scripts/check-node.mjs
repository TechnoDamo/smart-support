const major = Number.parseInt(process.versions.node.split('.')[0] ?? '', 10);

if (major !== 22) {
  console.error(
    [
      'This frontend is pinned to Node 22 LTS.',
      `Current Node version: ${process.versions.node}.`,
      'Run `nvm use 22` in /Users/damir/Desktop/smart-support/frontend-support and start the dev server again.',
    ].join('\n')
  );
  process.exit(1);
}
