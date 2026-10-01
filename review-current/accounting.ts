/**
 * ERPNext Accounting Tools
 *
 * MCP tools for accounting: accounts, journal entries, payment entries,
 * purchase orders, purchase invoices.
 *
 * @module lib/erpnext/tools/accounting
 */

import type { FrappeFilter } from "../api/types.ts";
import type { ErpNextTool } from "./types.ts";
import { DOC_META, DOCLIST_META } from "./viewer-meta.ts";
import { resolveDynamicLink } from "../api/resolve.ts";

export const accountingTools: ErpNextTool[] = [
  // ── Chart of Accounts ─────────────────────────────────────────────────────

  {
    name: "erpnext_account_list",
    annotations: { readOnlyHint: true },
    _meta: DOCLIST_META,
    description:
      "List Chart of Accounts. Filterable by root_type and is_group. " +
      "Fields: name, account_name, account_type, root_type, parent_account, is_group. " +
      "root_type values: Asset, Liability, Income, Expense, Equity.",
    category: "accounting",
    inputSchema: {
      type: "object",
      properties: {
        limit: { type: "number", description: "Max results (default 50)" },
        root_type: {
          type: "string",
          description:
            "Filter by root type: Asset, Liability, Income, Expense, Equity",
          enum: ["Asset", "Liability", "Income", "Expense", "Equity"],
        },
        is_group: {
          type: "boolean",
          description: "Filter by group accounts only",
        },
        company: { type: "string", description: "Filter by company" },
      },
    },
    handler: async (input, ctx) => {
      const limit = (input.limit as number) ?? 50;
      const filters: FrappeFilter[] = [];
      if (input.root_type) {
        filters.push(["root_type", "=", input.root_type as string]);
      }
      if (input.is_group !== undefined) {
        filters.push(["is_group", "=", (input.is_group as boolean) ? 1 : 0]);
      }
      if (input.company) {
        filters.push(["company", "=", input.company as string]);
      }

      const docs = await ctx.client.list("Account", {
        fields: [
          "name",
          "account_name",
          "account_type",
          "root_type",
          "parent_account",
          "is_group",
        ],
        filters,
        limit,
        order_by: "name asc",
      });

      return {
        doctype: "Account",
        count: docs.length,
        data: docs,
        _meta: DOCLIST_META,
      };
    },
  },

  // ── Journal Entries ───────────────────────────────────────────────────────

  {
    name: "erpnext_journal_entry_list",
    annotations: { readOnlyHint: true },
    _meta: DOCLIST_META,
    description:
      "List Journal Entries. Filterable by date range and voucher_type. " +
      "Fields: name, voucher_type, posting_date, total_debit, total_credit, remark.",
    category: "accounting",
    inputSchema: {
      type: "object",
      properties: {
        limit: { type: "number", description: "Max results (default 20)" },
        voucher_type: {
          type: "string",
          description:
            "Filter by voucher type (Journal Entry, Bank Entry, Cash Entry, etc.)",
        },
        date_from: {
          type: "string",
          description: "Start date filter YYYY-MM-DD",
        },
        date_to: { type: "string", description: "End date filter YYYY-MM-DD" },
      },
    },
    handler: async (input, ctx) => {
      const limit = (input.limit as number) ?? 20;
      const filters: FrappeFilter[] = [];
      if (input.voucher_type) {
        filters.push(["voucher_type", "=", input.voucher_type as string]);
      }
      if (input.date_from) {
        filters.push(["posting_date", ">=", input.date_from as string]);
      }
      if (input.date_to) {
        filters.push(["posting_date", "<=", input.date_to as string]);
      }

      const docs = await ctx.client.list("Journal Entry", {
        fields: [
          "name",
          "voucher_type",
          "posting_date",
          "total_debit",
          "total_credit",
          "remark",
        ],
        filters,
        limit,
        order_by: "modified desc",
      });

      return {
        doctype: "Journal Entry",
        count: docs.length,
        data: docs,
        _meta: DOCLIST_META,
      };
    },
  },

  {
    name: "erpnext_journal_entry_get",
    annotations: { readOnlyHint: true },
    _meta: DOC_META,
    description:
      "Get a single Journal Entry by name (e.g. JV-00001). Returns full document with accounts.",
    category: "accounting",
    inputSchema: {
      type: "object",
      properties: {
        name: {
          type: "string",
          description: "Journal Entry name (e.g. JV-00001)",
        },
      },
      required: ["name"],
    },
    handler: async (input, ctx) => {
      if (!input.name) {
        throw new Error("[erpnext_journal_entry_get] 'name' is required");
      }
      const doc = await ctx.client.get("Journal Entry", input.name as string);
      return { data: { ...doc, doctype: "Journal Entry" } };
    },
  },

  // ── Payment Entries ───────────────────────────────────────────────────────

  {
    name: "erpnext_payment_entry_list",
    annotations: { readOnlyHint: true },
    _meta: DOCLIST_META,
    description:
      "List Payment Entries. Filterable by payment_type, party_type, date range. " +
      "Fields: name, payment_type, party_type, party, posting_date, paid_amount, currency. " +
      "payment_type values: Receive, Pay, Internal Transfer.",
    category: "accounting",
    inputSchema: {
      type: "object",
      properties: {
        limit: { type: "number", description: "Max results (default 20)" },
        payment_type: {
          type: "string",
          description:
            "Filter by payment type: Receive, Pay, Internal Transfer",
          enum: ["Receive", "Pay", "Internal Transfer"],
        },
        party_type: {
          type: "string",
          description: "Filter by party type (Customer, Supplier, Employee). " +
            "Required when 'party' is set, so the party name/ID can be resolved against the right doctype.",
          enum: ["Customer", "Supplier", "Employee"],
        },
        party: {
          type: "string",
          description:
            "Filter by party — ID or name (e.g. 'CUST-00001' or 'Acme Corp'). Requires 'party_type'.",
        },
        date_from: {
          type: "string",
          description: "Start date filter YYYY-MM-DD",
        },
      },
    },
    handler: async (input, ctx) => {
      const limit = (input.limit as number) ?? 20;
      const filters: FrappeFilter[] = [];
      if (input.payment_type) {
        filters.push(["payment_type", "=", input.payment_type as string]);
      }
      if (input.party_type) {
        filters.push(["party_type", "=", input.party_type as string]);
      }
      if (input.party) {
        if (!input.party_type) {
          throw new Error(
            "[erpnext_payment_entry_list] 'party_type' is required when filtering by 'party'",
          );
        }
        filters.push([
          "party",
          "=",
          await resolveDynamicLink(
            ctx.client,
            input.party_type as string,
            input.party as string,
            { inputPath: "party" },
          ),
        ]);
      }
      if (input.date_from) {
        filters.push(["posting_date", ">=", input.date_from as string]);
      }

      const docs = await ctx.client.list("Payment Entry", {
        fields: [
          "name",
          "payment_type",
          "party_type",
          "party",
          "posting_date",
          "paid_amount",
          "currency",
        ],
        filters,
        limit,
        order_by: "modified desc",
      });

      return {
        doctype: "Payment Entry",
        count: docs.length,
        data: docs,
        _meta: DOCLIST_META,
      };
    },
  },

  {
    name: "erpnext_payment_entry_get",
    annotations: { readOnlyHint: true },
    _meta: DOC_META,
    description:
      "Get a single Payment Entry by name (e.g. PE-00001). Returns full document including references.",
    category: "accounting",
    inputSchema: {
      type: "object",
      properties: {
        name: {
          type: "string",
          description: "Payment Entry name (e.g. PE-00001)",
        },
      },
      required: ["name"],
    },
    handler: async (input, ctx) => {
      if (!input.name) {
        throw new Error("[erpnext_payment_entry_get] 'name' is required");
      }
      const doc = await ctx.client.get("Payment Entry", input.name as string);
      return { data: { ...doc, doctype: "Payment Entry" } };
    },
  },

  {
    name: "erpnext_payment_entry_create",
    description:
      "Create and optionally submit a Payment Entry for a Customer, Supplier, or Employee. " +
      "For Employee Advances, uses the official HRMS Employee Advance payment builder.",
    category: "accounting",
    inputSchema: {
      type: "object",
      properties: {
        payment_type: {
          type: "string",
          description: "Payment type",
          enum: ["Receive", "Pay", "Internal Transfer"],
        },
        party_type: {
          type: "string",
          description: "Party type",
          enum: ["Customer", "Supplier", "Employee"],
        },
        party: {
          type: "string",
          description: "Party ID or name",
        },
        employee_advance: {
          type: "string",
          description:
            "Employee Advance ID. When supplied, the official HRMS payment builder is used.",
        },
        paid_from: {
          type: "string",
          description:
            "Source bank/cash ledger account. Required for Employee Advance payment.",
        },
        paid_to: {
          type: "string",
          description:
            "Target ledger account. For Employee Advance HRMS determines this from advance_account.",
        },
        paid_amount: {
          type: "number",
          description: "Payment amount",
        },
        posting_date: {
          type: "string",
          description: "Posting date YYYY-MM-DD",
        },
        reference_no: {
          type: "string",
          description: "Payment reference number",
        },
        reference_date: {
          type: "string",
          description: "Payment reference date YYYY-MM-DD",
        },
        submit: {
          type: "boolean",
          description:
            "Submit the Payment Entry after creation. Default false unless explicitly requested.",
        },
      },
      required: ["paid_amount"],
    },
    handler: async (input, ctx) => {
      const amount = Number(input.paid_amount);

      if (!Number.isFinite(amount) || amount <= 0) {
        throw new Error(
          "[erpnext_payment_entry_create] 'paid_amount' must be a positive number",
        );
      }

      /*
       * Employee Advance:
       * Use the official HRMS builder instead of manually constructing
       * Payment Entry references/accounts.
       */
      if (input.employee_advance) {
        const advanceId = input.employee_advance as string;

        if (!input.paid_from) {
          throw new Error(
            "[erpnext_payment_entry_create] 'paid_from' is required for Employee Advance payment",
          );
        }

        const advance = await ctx.client.get(
          "Employee Advance",
          advanceId,
          { skipCache: true },
        );

        const outstanding =
          Number(advance.advance_amount ?? 0) -
          Number(advance.paid_amount ?? 0);

        if (Number(advance.docstatus) === 2) {
          throw new Error(
            `[erpnext_payment_entry_create] Employee Advance ${advanceId} is cancelled`,
          );
        }

        if (outstanding <= 0) {
          throw new Error(
            `[erpnext_payment_entry_create] Employee Advance ${advanceId} has no outstanding amount`,
          );
        }

        if (amount > outstanding + 0.000001) {
          throw new Error(
            `[erpnext_payment_entry_create] Requested payment ${amount} exceeds outstanding advance amount ${outstanding}`,
          );
        }

        const bankAccount = input.paid_from as string;

        const account = await ctx.client.get(
          "Account",
          bankAccount,
          { skipCache: true },
        );

        if (Number(account.is_group) === 1) {
          throw new Error(
            `[erpnext_payment_entry_create] paid_from '${bankAccount}' is a group account; a ledger account is required`,
          );
        }

        if (account.company && account.company !== advance.company) {
          throw new Error(
            `[erpnext_payment_entry_create] paid_from '${bankAccount}' does not belong to company '${advance.company}'`,
          );
        }

        /*
         * Official HRMS function:
         * hrms.overrides.employee_payment_entry.get_payment_entry_for_employee
         *
         * This function builds:
         * - paid_from
         * - paid_to
         * - party
         * - currencies
         * - references
         * - total_amount
         * - outstanding_amount
         * - allocated_amount
         * - exchange rates
         * - amounts
         */
        const built = await ctx.client.callMethod(
          "hrms.overrides.employee_payment_entry.get_payment_entry_for_employee",
          {
            dt: "Employee Advance",
            dn: advanceId,
            party_amount: amount,
            bank_account: bankAccount,
          },
        );

        const paymentDoc =
          (built as Record<string, unknown>)?.message ??
          built;

        if (
          !paymentDoc ||
          typeof paymentDoc !== "object" ||
          (paymentDoc as Record<string, unknown>).doctype !== "Payment Entry"
        ) {
          throw new Error(
            `[erpnext_payment_entry_create] HRMS did not return a valid Payment Entry for ${advanceId}`,
          );
        }

        const paymentData = paymentDoc as Record<string, unknown>;

        if (input.posting_date) {
          paymentData.posting_date = input.posting_date as string;
        }

        paymentData.reference_no =
          (input.reference_no as string | undefined) ||
          `EMP-ADV-${advanceId}`;

        paymentData.reference_date =
          (input.reference_date as string | undefined) ||
          (paymentData.posting_date as string) ||
          new Date().toISOString().slice(0, 10);

        const created = await ctx.client.create(
          "Payment Entry",
          paymentData,
        );

        if (!created?.name) {
          throw new Error(
            `[erpnext_payment_entry_create] Payment Entry was not created for ${advanceId}`,
          );
        }

        if (input.submit === true) {
          const fresh = await ctx.client.get(
            "Payment Entry",
            created.name as string,
            { skipCache: true },
          );

          await ctx.client.callMethod(
            "frappe.client.submit",
            { doc: fresh },
          );
        }

        const verifiedPayment = await ctx.client.get(
          "Payment Entry",
          created.name as string,
          { skipCache: true },
        );

        const verifiedAdvance = await ctx.client.get(
          "Employee Advance",
          advanceId,
          { skipCache: true },
        );

        return {
          data: {
            payment_entry: {
              ...verifiedPayment,
              doctype: "Payment Entry",
            },
            employee_advance: {
              ...verifiedAdvance,
              doctype: "Employee Advance",
            },
          },
          message:
            `Employee Advance ${advanceId}: Payment Entry ${created.name} ` +
            `${Number(verifiedPayment.docstatus) === 1 ? "created and submitted" : "created as draft"} successfully`,
        };
      }

      /*
       * Normal Customer / Supplier / Employee Payment Entry flow.
       */
      let paymentType =
        (input.payment_type as string | undefined) ?? "Pay";
      let partyType = input.party_type as string | undefined;
      let party = input.party as string | undefined;
      let company: string | undefined;
      let paidTo = input.paid_to as string | undefined;

      if (!company && partyType && party) {
        const resolvedParty = await resolveDynamicLink(
          ctx.client,
          partyType,
          party,
          { inputPath: "party" },
        );

        party = resolvedParty;

        const partyDoc = await ctx.client.get(
          partyType,
          resolvedParty,
          { skipCache: true },
        );

        company = partyDoc.company as string | undefined;
      }

      if (!partyType || !party) {
        throw new Error(
          "[erpnext_payment_entry_create] 'party_type' and 'party' are required",
        );
      }

      if (!company) {
        throw new Error(
          "[erpnext_payment_entry_create] Company could not be determined",
        );
      }

      const validateLedgerAccount = async (
        accountName: string,
        field: string,
      ) => {
        const account = await ctx.client.get(
          "Account",
          accountName,
          { skipCache: true },
        );

        if (Number(account.is_group) === 1) {
          throw new Error(
            `[erpnext_payment_entry_create] ${field} '${accountName}' is a group account; a ledger account is required`,
          );
        }

        if (account.company && account.company !== company) {
          throw new Error(
            `[erpnext_payment_entry_create] ${field} '${accountName}' does not belong to company '${company}'`,
          );
        }
      };

      if (!input.paid_from) {
        throw new Error(
          "[erpnext_payment_entry_create] 'paid_from' is required",
        );
      }

      const paidFrom = input.paid_from as string;

      await validateLedgerAccount(paidFrom, "paid_from");

      if (!paidTo) {
        throw new Error(
          "[erpnext_payment_entry_create] 'paid_to' is required",
        );
      }

      await validateLedgerAccount(paidTo, "paid_to");

      const data: Record<string, unknown> = {
        payment_type: paymentType,
        party_type: partyType,
        party,
        company,
        paid_from: paidFrom,
        paid_to: paidTo,
        paid_amount: amount,
        received_amount: amount,
      };

      if (input.posting_date) {
        data.posting_date = input.posting_date as string;
      }

      if (input.reference_no) {
        data.reference_no = input.reference_no as string;
      }

      if (input.reference_date) {
        data.reference_date = input.reference_date as string;
      }

      const doc = await ctx.client.create(
        "Payment Entry",
        data,
      );

      if (input.submit === true) {
        const fresh = await ctx.client.get(
          "Payment Entry",
          doc.name as string,
          { skipCache: true },
        );

        await ctx.client.callMethod(
          "frappe.client.submit",
          { doc: fresh },
        );
      }

      const verified = await ctx.client.get(
        "Payment Entry",
        doc.name as string,
        { skipCache: true },
      );

      return {
        data: {
          ...verified,
          doctype: "Payment Entry",
        },
        message:
          `Payment Entry ${doc.name} ` +
          `${Number(verified.docstatus) === 1 ? "created and submitted" : "created as draft"} successfully`,
      };
    },
  },
  {
    name: "erpnext_journal_entry_create",
    description:
      "Create a new Journal Entry. Requires voucher_type and accounts with debit/credit amounts. " +
      "Total debits must equal total credits.",
    category: "accounting",
    inputSchema: {
      type: "object",
      properties: {
        voucher_type: {
          type: "string",
          description:
            "Journal entry type (Journal Entry, Bank Entry, Cash Entry, Credit Card Entry, etc.)",
        },
        accounts: {
          type: "array",
          description:
            "Account entries: [{account, debit_in_account_currency, credit_in_account_currency}]",
          items: {
            type: "object",
            properties: {
              account: { type: "string", description: "Account name" },
              debit_in_account_currency: {
                type: "number",
                description: "Debit amount (0 if credit)",
              },
              credit_in_account_currency: {
                type: "number",
                description: "Credit amount (0 if debit)",
              },
            },
            required: ["account"],
          },
        },
        posting_date: {
          type: "string",
          description: "Posting date YYYY-MM-DD (default: today)",
        },
        remark: { type: "string", description: "Narration / remark" },
      },
      required: ["voucher_type", "accounts"],
    },
    handler: async (input, ctx) => {
      if (!input.voucher_type) {
        throw new Error(
          "[erpnext_journal_entry_create] 'voucher_type' is required",
        );
      }
      if (
        !input.accounts || !Array.isArray(input.accounts) ||
        input.accounts.length === 0
      ) {
        throw new Error(
          "[erpnext_journal_entry_create] 'accounts' must be a non-empty array",
        );
      }

      const data: Record<string, unknown> = {
        voucher_type: input.voucher_type as string,
        accounts: input.accounts,
      };
      if (input.posting_date) data.posting_date = input.posting_date as string;
      if (input.remark) data.remark = input.remark as string;

      const doc = await ctx.client.create("Journal Entry", data);
      return {
        data: doc,
        message: `Journal Entry ${doc.name} created successfully`,
      };
    },
  },
];
