import "./globals.css";
import { RadarProvider } from "@/lib/RadarContext";
import { PlayerProvider } from "@/lib/PlayerContext";
import TopBar from "@/components/TopBar";
import Toasts from "@/components/Toasts";

export const metadata = {
  title: "SongRadar",
  description:
    "Recognizes whatever music is playing around you or on your PC, and files it into playlists.",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>
        <div className="backdrop" />
        <RadarProvider>
          <PlayerProvider>
            <TopBar />
            {children}
            <Toasts />
          </PlayerProvider>
        </RadarProvider>
      </body>
    </html>
  );
}
