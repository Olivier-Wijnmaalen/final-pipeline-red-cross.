import type {Metadata} from "next"; import "./globals.css";
export const metadata:Metadata={title:"DEMA internal demonstration",description:"Evidence-grounded documentary pre-assessment pipeline"};
export default function Layout({children}:{children:React.ReactNode}){return <html lang="en"><body>{children}</body></html>}
