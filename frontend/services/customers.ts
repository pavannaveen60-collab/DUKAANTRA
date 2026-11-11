import { apiRequest } from "@/lib/api";
import { getActiveShopId } from "@/lib/shop-context";

function customerPath(customerId?: string) {
  const base = `/api/v1/shops/${getActiveShopId()}/customers/`;
  return customerId ? `${base}${customerId}` : base;
}

export interface Customer {
  id: string;
  shop_id: string;
  full_name: string;
  phone: string | null;
  email: string | null;
  address: string | null;
  created_at: string;
}

export interface CustomerInput {
  full_name: string;
  phone?: string | null;
  email?: string | null;
  address?: string | null;
}

export async function fetchCustomers() {
  return apiRequest<Customer[]>(customerPath());
}

export async function fetchCustomer(customerId: string) {
  return apiRequest<Customer>(customerPath(customerId));
}

export async function createCustomer(data: CustomerInput) {
  return apiRequest<Customer>(customerPath(), {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export async function updateCustomer(
  customerId: string,
  data: Partial<CustomerInput>,
) {
  return apiRequest<Customer>(customerPath(customerId), {
    method: "PATCH",
    body: JSON.stringify(data),
  });
}

export async function deleteCustomer(customerId: string) {
  return apiRequest<unknown>(customerPath(customerId), {
    method: "DELETE",
  });
}
