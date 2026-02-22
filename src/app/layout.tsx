import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
    title: "Portfolio Risk",
    description: "Analyze your portfolio risk and compare it with other portfolios.",
};

export default function RootLayout({
    children,
}: {
    children: React.ReactNode;
}) {
    return (
        <html lang="en">
            <body>{children}</body>
        </html>
    );
}
