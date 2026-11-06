import type { Schemas } from "./client";

export type Me = Schemas["MeOut"];
export type User = Schemas["UserOut"];
export type Borrower = Schemas["BorrowerOut"];
export type BorrowerDetail = Schemas["BorrowerDetailOut"];
export type BorrowerListItem = Schemas["BorrowerListItem"];
export type SearchResult = Schemas["SearchResult"];
export type LoanDetail = Schemas["LoanDetailOut"];
export type LoanListItem = Schemas["LoanListItem"];
export type Payment = Schemas["PaymentOut"];
export type Preview = Schemas["PreviewOut"];
export type TermsIn = Schemas["TermsIn"];
export type PreviewIn = Schemas["PreviewIn"];
export type ChargeIn = Schemas["ChargeIn"];
export type SecurityIn = Schemas["SecurityIn"];
export type SecurityOut = Schemas["SecurityOut"];
export type ChargeOut = Schemas["ChargeOut"];
export type ScheduleItem = Schemas["ScheduleItemOut"];
export type Settlement = Schemas["SettlementOut"];
export type Reminder = Schemas["ReminderOut"];
export type DocumentOut = Schemas["DocumentOut"];
export type Category = Schemas["CategoryOut"];

export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

export interface DueRow {
  loan_id: string;
  loan_no: string;
  borrower_id: string;
  code: string;
  name_en: string | null;
  name_ta: string | null;
  phone: string | null;
  preferred_language: "en" | "ta";
  amount_due: string;
  due_date: string | null;
  overdue_amount: string;
  overdue_days: number;
  bucket: string;
  last_payment_on: string | null;
  days_since_last_payment: number;
  multiple_overdue: boolean;
  penalty_due: string;
  outstanding: string;
}

export interface DaybookEntry {
  date: string;
  direction: "in" | "out";
  source_type: "payment" | "loan" | "cash_entry" | "loan_charge";
  source_id: string;
  kind: "payment" | "reversal" | "settlement" | "loan" | "income" | "expense" | "charge";
  treatment?: "deducted" | "added";
  amount: string;
  mode: string;
  loan_id: string | null;
  loan_no: string | null;
  code: string | null;
  name_en: string | null;
  name_ta: string | null;
  receipt_no: string | null;
  principal: string | null;
  interest: string | null;
  penalty: string | null;
  category_en: string | null;
  category_ta: string | null;
  note: string | null;
  version?: number;
}

export interface Daybook {
  date: string;
  tracked: boolean;
  balance_start_date: string | null;
  opening_balance: string | null;
  money_in: string;
  money_out: string;
  net: string;
  closing_balance: string | null;
  by_mode: Record<string, { in: string; out: string }>;
  week: { start: string; in: string; out: string; net: string };
  month: { start: string; in: string; out: string; net: string };
  entries_in: DaybookEntry[];
  entries_out: DaybookEntry[];
}

export interface Dashboard {
  principal_outstanding: string;
  principal_lent_active: string;
  total_to_receive: string;
  collected_this_month: { principal: string; interest: string; penalty: string; total: string };
  interest_this_month: string;
  interest_to_date: string;
  due_today: { count: number; amount: string };
  overdue: { count: number; amount: string };
  upcoming: { count: number; amount: string };
  long_unpaid: { count: number };
  ageing: Record<string, { count: number; amount: string }>;
  active_loans: number;
  active_borrowers: number;
}

export interface AppSettings {
  version: number;
  licence_no: string | null;
  lender_name: string | null;
  lender_address: string | null;
  max_rate_monthly: string | null;
  due_soon_days: number;
  due_window_days: number;
  long_unpaid_days: number;
  default_language: "en" | "ta";
  balance_start_date: string | null;
  opening_balance: string;
  penalty_default_mode: "off" | "per_day" | "pct_month";
  penalty_default_value: string;
  penalty_grace_days: number;
  staff_enabled: boolean;
  staff_can_create_loans: boolean;
  daily_summary_time: string | null;
  retention_years: number;
  max_upload_mb: number;
  max_files_per_owner: number;
  ltv_max_vehicle: string;
  ltv_max_land: string;
  emi_rounding_default: string;
  broken_period_default: "none" | "first_installment" | "upfront";
  advance_installments_default: number;
  processing_fee_percent: string;
  document_charges_default: string;
}

export interface ImportSummary {
  loans: number;
  borrowers: number;
  payments: number;
  total_principal: string;
  total_payable: string;
  total_paid: string;
  total_outstanding: string;
  missing_aadhaar: number;
  errors: { sheet: string; row: number; field: string; code: string }[];
  rows: { row: number; ref: string; name_en: string | null; name_ta: string | null; phone: string;
    principal: string; method: string; disbursal_date: string; payments: number; paid: string;
    outstanding: string }[];
}
