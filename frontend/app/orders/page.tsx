
import MerchantDashboard from "@/components/merchant-dashboard";
import OrdersManagement from "@/components/orders-management";

export default function OrdersPage() {
  return (
    <MerchantDashboard>
      <OrdersManagement />
    </MerchantDashboard>
  );
}
