import { apiRequest } from "@/lib/api";

export interface Shop {
  id: string;
  owner_id: string;
  shop_name: string;
  business_type: string;
  phone: string | null;
  address: string | null;
  city: string | null;
  state: string | null;
  pincode: string | null;
}

export interface ShopCreateInput {
  shop_name: string;
  business_type: string;
  phone: string;
  address: string;
}

export function fetchMyShops(): Promise<Shop[]> {
  return apiRequest<Shop[]>("/api/v1/shops/");
}

export function createShop(data: ShopCreateInput): Promise<Shop> {
  return apiRequest<Shop>("/api/v1/shops/", {
    method: "POST",
    body: JSON.stringify({
      ...data,
      shop_name: data.shop_name.trim(),
      business_type: data.business_type.trim(),
      phone: data.phone.trim(),
      address: data.address.trim(),
    }),
  });
}
