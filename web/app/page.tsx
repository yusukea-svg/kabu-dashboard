import LastUpdated from "@/components/LastUpdated";
import SignalList from "@/components/SignalList";
import StockList from "@/components/StockList";

export default function Home() {
  return (
    <>
      <LastUpdated />
      <SignalList />
      <StockList />
    </>
  );
}
