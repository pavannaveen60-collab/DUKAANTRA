"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Users,
  UserRound,
  UserPlus,
  Search,
  RefreshCw,
  Mail,
  Phone,
  MapPin,
  Pencil,
  Trash2,
  X,
  UsersRound,
  CalendarDays,
  AlertCircle,
  CheckCircle2,
} from "lucide-react";

import {
  Customer,
  CustomerInput,
  fetchCustomers,
  createCustomer,
  updateCustomer,
  deleteCustomer,
} from "@/services/customers";

type FormState = {
  full_name: string;
  phone: string;
  email: string;
  address: string;
};

const emptyForm: FormState = {
  full_name: "",
  phone: "",
  email: "",
  address: "",
};

function formatDate(value: string) {
  return new Intl.DateTimeFormat("en-IN", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  }).format(new Date(value));
}

function initials(name: string) {
  return name
    .trim()
    .split(/\s+/)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? "")
    .join("");
}

export default function CustomersManagement() {
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [search, setSearch] = useState("");
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<Customer | null>(null);
  const [form, setForm] = useState<FormState>(emptyForm);
  const [saving, setSaving] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  const loadCustomers = useCallback(async (showRefresh = false) => {
    if (showRefresh) setRefreshing(true);
    else setLoading(true);

    setError("");

    try {
      const result = await fetchCustomers();
      setCustomers(result);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Unable to load customers.",
      );
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    void loadCustomers();
  }, [loadCustomers]);

  const filteredCustomers = useMemo(() => {
    const query = search.trim().toLowerCase();

    if (!query) return customers;

    return customers.filter((customer) =>
      [
        customer.full_name,
        customer.phone,
        customer.email,
        customer.address,
      ]
        .filter(Boolean)
        .some((value) => String(value).toLowerCase().includes(query)),
    );
  }, [customers, search]);

  const withPhone = customers.filter((customer) => customer.phone).length;
  const withEmail = customers.filter((customer) => customer.email).length;

  function openCreate() {
    setEditing(null);
    setForm(emptyForm);
    setError("");
    setModalOpen(true);
  }

  function openEdit(customer: Customer) {
    setEditing(customer);
    setForm({
      full_name: customer.full_name,
      phone: customer.phone ?? "",
      email: customer.email ?? "",
      address: customer.address ?? "",
    });
    setError("");
    setModalOpen(true);
  }

  function closeModal() {
    if (saving) return;
    setModalOpen(false);
    setEditing(null);
    setForm(emptyForm);
  }

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();

    const name = form.full_name.trim();

    if (name.length < 2) {
      setError("Customer name must contain at least 2 characters.");
      return;
    }

    const payload: CustomerInput = {
      full_name: name,
      phone: form.phone.trim() || null,
      email: form.email.trim() || null,
      address: form.address.trim() || null,
    };

    setSaving(true);
    setError("");

    try {
      if (editing) {
        await updateCustomer(editing.id, payload);
        setSuccess("Customer details updated successfully.");
      } else {
        await createCustomer(payload);
        setSuccess("Customer added successfully.");
      }

      setModalOpen(false);
      setEditing(null);
      setForm(emptyForm);
      await loadCustomers(true);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Unable to save customer.",
      );
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(customer: Customer) {
    const confirmed = window.confirm(
      `Delete ${customer.full_name} from your customer directory?`,
    );

    if (!confirmed) return;

    setDeletingId(customer.id);
    setError("");
    setSuccess("");

    try {
      await deleteCustomer(customer.id);
      setCustomers((current) =>
        current.filter((item) => item.id !== customer.id),
      );
      setSuccess("Customer deleted successfully.");
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Unable to delete customer.",
      );
    } finally {
      setDeletingId(null);
    }
  }

  return (
    <div className="customers-page">
      <div className="customers-heading">
        <div>
          <span className="eyebrow">CUSTOMER RELATIONSHIPS</span>
          <h1>Customers</h1>
          <p>Know your customers. Build stronger business relationships.</p>
        </div>

        <div className="customers-heading-actions">
          <button
            className="customers-secondary-button"
            onClick={() => void loadCustomers(true)}
            disabled={refreshing}
          >
            <RefreshCw size={15} className={refreshing ? "spin" : ""} />
            Refresh
          </button>

          <button className="customers-primary-button" onClick={openCreate}>
            <UserPlus size={16} />
            Add customer
          </button>
        </div>
      </div>

      {error && !modalOpen && (
        <div className="customers-alert customers-alert-error">
          <AlertCircle size={16} />
          {error}
          <button onClick={() => setError("")} aria-label="Dismiss error">
            <X size={15} />
          </button>
        </div>
      )}

      {success && (
        <div className="customers-alert customers-alert-success">
          <CheckCircle2 size={16} />
          {success}
          <button onClick={() => setSuccess("")} aria-label="Dismiss message">
            <X size={15} />
          </button>
        </div>
      )}

      <section className="customers-stats">
        <article className="customers-stat-card">
          <div className="customers-stat-icon">
            <Users size={18} />
          </div>
          <span>Total customers</span>
          <strong>{customers.length}</strong>
          <small>Customers in your directory</small>
        </article>

        <article className="customers-stat-card">
          <div className="customers-stat-icon customers-stat-blue">
            <Phone size={18} />
          </div>
          <span>Phone numbers</span>
          <strong>{withPhone}</strong>
          <small>Customers with contact numbers</small>
        </article>

        <article className="customers-stat-card">
          <div className="customers-stat-icon customers-stat-purple">
            <Mail size={18} />
          </div>
          <span>Email contacts</span>
          <strong>{withEmail}</strong>
          <small>Customers with email addresses</small>
        </article>

        <article className="customers-stat-card">
          <div className="customers-stat-icon customers-stat-orange">
            <UsersRound size={18} />
          </div>
          <span>Contact coverage</span>
          <strong>
            {customers.length
              ? Math.round(
                  (customers.filter((c) => c.phone || c.email).length /
                    customers.length) *
                    100,
                )
              : 0}
            %
          </strong>
          <small>Customers with at least one contact</small>
        </article>
      </section>

      <section className="customers-workspace">
        <div className="customers-table-heading">
          <div>
            <span className="eyebrow">CUSTOMER DIRECTORY</span>
            <h2>All customers</h2>
            <p>Manage your customer information in one place.</p>
          </div>
          <span className="customers-count">
            {filteredCustomers.length}{" "}
            {filteredCustomers.length === 1 ? "customer" : "customers"}
          </span>
        </div>

        <div className="customers-toolbar">
          <div className="customers-search">
            <Search size={16} />
            <input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Search by name, phone, email or address..."
              aria-label="Search customers"
            />
            {search && (
              <button onClick={() => setSearch("")} aria-label="Clear search">
                <X size={14} />
              </button>
            )}
          </div>
        </div>

        {loading ? (
          <div className="customers-empty">
            <RefreshCw size={22} className="spin" />
            <span>Loading customer directory...</span>
          </div>
        ) : filteredCustomers.length === 0 ? (
          <div className="customers-empty">
            <div className="customers-empty-icon">
              <UserRound size={24} />
            </div>
            <strong>
              {search ? "No matching customers" : "Your customer directory is empty"}
            </strong>
            <span>
              {search
                ? "Try another name, phone number or email."
                : "Add your first customer to start building your directory."}
            </span>
            {!search && (
              <button className="customers-primary-button" onClick={openCreate}>
                <UserPlus size={15} />
                Add first customer
              </button>
            )}
          </div>
        ) : (
          <div className="customers-table-wrap">
            <table className="customers-table">
              <thead>
                <tr>
                  <th>CUSTOMER</th>
                  <th>PHONE</th>
                  <th>EMAIL</th>
                  <th>ADDRESS</th>
                  <th>ADDED ON</th>
                  <th className="customers-actions-heading">ACTIONS</th>
                </tr>
              </thead>
              <tbody>
                {filteredCustomers.map((customer) => (
                  <tr key={customer.id}>
                    <td>
                      <div className="customers-person">
                        <span className="customers-avatar">
                          {initials(customer.full_name)}
                        </span>
                        <div>
                          <strong>{customer.full_name}</strong>
                          <small>Customer</small>
                        </div>
                      </div>
                    </td>
                    <td>
                      {customer.phone ? (
                        <span className="customers-contact">
                          <Phone size={13} />
                          {customer.phone}
                        </span>
                      ) : (
                        <span className="customers-muted">Not provided</span>
                      )}
                    </td>
                    <td>
                      {customer.email ? (
                        <span className="customers-contact">
                          <Mail size={13} />
                          {customer.email}
                        </span>
                      ) : (
                        <span className="customers-muted">Not provided</span>
                      )}
                    </td>
                    <td>
                      {customer.address ? (
                        <span className="customers-address">
                          <MapPin size={13} />
                          {customer.address}
                        </span>
                      ) : (
                        <span className="customers-muted">Not provided</span>
                      )}
                    </td>
                    <td>
                      <span className="customers-date">
                        <CalendarDays size={13} />
                        {formatDate(customer.created_at)}
                      </span>
                    </td>
                    <td>
                      <div className="customers-row-actions">
                        <button
                          onClick={() => openEdit(customer)}
                          title="Edit customer"
                          aria-label={`Edit ${customer.full_name}`}
                        >
                          <Pencil size={15} />
                        </button>
                        <button
                          className="customers-delete-action"
                          onClick={() => void handleDelete(customer)}
                          disabled={deletingId === customer.id}
                          title="Delete customer"
                          aria-label={`Delete ${customer.full_name}`}
                        >
                          {deletingId === customer.id ? (
                            <RefreshCw size={15} className="spin" />
                          ) : (
                            <Trash2 size={15} />
                          )}
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {!loading && customers.length > 0 && (
          <div className="customers-table-footer">
            Showing {filteredCustomers.length} of {customers.length} customers
          </div>
        )}
      </section>

      {modalOpen && (
        <div
          className="customers-modal-backdrop"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) closeModal();
          }}
        >
          <section
            className="customers-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="customer-modal-title"
          >
            <header className="customers-modal-header">
              <div>
                <span className="eyebrow">
                  {editing ? "CUSTOMER DETAILS" : "NEW RELATIONSHIP"}
                </span>
                <h2 id="customer-modal-title">
                  {editing ? "Edit customer" : "Add customer"}
                </h2>
                <p>
                  {editing
                    ? "Update the customer's contact information."
                    : "Add a customer to your business directory."}
                </p>
              </div>
              <button
                className="customers-modal-close"
                onClick={closeModal}
                disabled={saving}
                aria-label="Close dialog"
              >
                <X size={18} />
              </button>
            </header>

            <form className="customers-form" onSubmit={handleSubmit}>
              {error && (
                <div className="customers-alert customers-alert-error">
                  <AlertCircle size={15} />
                  {error}
                </div>
              )}

              <label className="customers-field">
                Full name <span>*</span>
                <input
                  autoFocus
                  required
                  minLength={2}
                  maxLength={150}
                  value={form.full_name}
                  onChange={(event) =>
                    setForm({ ...form, full_name: event.target.value })
                  }
                  placeholder="Enter customer's full name"
                />
              </label>

              <div className="customers-form-grid">
                <label className="customers-field">
                  Phone number
                  <input
                    type="tel"
                    maxLength={20}
                    value={form.phone}
                    onChange={(event) =>
                      setForm({ ...form, phone: event.target.value })
                    }
                    placeholder="+91 98765 43210"
                  />
                </label>

                <label className="customers-field">
                  Email address
                  <input
                    type="email"
                    value={form.email}
                    onChange={(event) =>
                      setForm({ ...form, email: event.target.value })
                    }
                    placeholder="customer@example.com"
                  />
                </label>
              </div>

              <label className="customers-field">
                Address
                <textarea
                  rows={3}
                  maxLength={255}
                  value={form.address}
                  onChange={(event) =>
                    setForm({ ...form, address: event.target.value })
                  }
                  placeholder="Enter customer address"
                />
              </label>

              <div className="customers-form-note">
                <span>*</span> Full name is required. Other contact details are optional.
              </div>

              <div className="customers-modal-actions">
                <button
                  type="button"
                  className="customers-secondary-button"
                  onClick={closeModal}
                  disabled={saving}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="customers-primary-button"
                  disabled={saving}
                >
                  {saving ? (
                    <>
                      <RefreshCw size={15} className="spin" />
                      Saving...
                    </>
                  ) : (
                    <>
                      {editing ? <Pencil size={15} /> : <UserPlus size={15} />}
                      {editing ? "Save changes" : "Add customer"}
                    </>
                  )}
                </button>
              </div>
            </form>
          </section>
        </div>
      )}
    </div>
  );
}
