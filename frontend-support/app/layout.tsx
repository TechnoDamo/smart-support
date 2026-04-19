import type { Metadata } from 'next';

import './globals.css';

export const metadata: Metadata = {
  title: 'Smart Support Workspace',
  description: 'Support workspace for tickets, chats, AI suggestions and knowledge base'
};

export default function RootLayout({
  children
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body>{children}</body>
    </html>
  );
}
