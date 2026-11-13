using System;
using System.Collections.Generic;

namespace Acme.Warehouse
{
    /// <summary>
    /// Tracks stock levels per SKU and emits reorder suggestions.
    /// </summary>
    public class InventoryLedger
    {
        private readonly Dictionary<string, int> stock = new Dictionary<string, int>();
        private readonly Dictionary<string, int> reorderPoint = new Dictionary<string, int>();
        private readonly List<string> auditLog = new List<string>();
        private int movementCount = 0;

        public void RegisterSku(string sku, int initialQty, int reorderAt)
        {
            if (sku == null || sku.Length == 0)
            {
                throw new ArgumentException("sku must not be empty");
            }
            if (initialQty < 0 || reorderAt < 0)
            {
                throw new ArgumentException("quantities must be non-negative");
            }
            stock[sku] = initialQty;
            reorderPoint[sku] = reorderAt;
            auditLog.Add("REGISTER " + sku + " qty=" + initialQty);
        }

        public int Receive(string sku, int qty)
        {
            RequireKnown(sku);
            if (qty <= 0)
            {
                throw new ArgumentException("receive qty must be positive");
            }
            int updated = stock[sku] + qty;
            stock[sku] = updated;
            movementCount++;
            auditLog.Add("RECEIVE " + sku + " +" + qty + " -> " + updated);
            return updated;
        }

        public int Ship(string sku, int qty)
        {
            RequireKnown(sku);
            int current = stock[sku];
            if (qty > current)
            {
                auditLog.Add("SHORT " + sku + " wanted=" + qty + " have=" + current);
                throw new InvalidOperationException("insufficient stock for " + sku);
            }
            int updated = current - qty;
            stock[sku] = updated;
            movementCount++;
            auditLog.Add("SHIP " + sku + " -" + qty + " -> " + updated);
            return updated;
        }

        public List<string> ReorderSuggestions(int batchSize)
        {
            List<string> result = new List<string>();
            foreach (KeyValuePair<string, int> entry in stock)
            {
                string sku = entry.Key;
                int qty = entry.Value;
                int point = reorderPoint[sku];
                if (qty <= point)
                {
                    int deficit = point - qty;
                    int batches = deficit / batchSize + 1;
                    result.Add(sku + ":" + (batches * batchSize));
                }
            }
            result.Sort(string.CompareOrdinal);
            return result;
        }

        public double TurnoverRatio(string sku, int periodShipped)
        {
            RequireKnown(sku);
            int onHand = stock[sku];
            if (onHand == 0)
            {
                return double.PositiveInfinity;
            }
            return (double) periodShipped / onHand;
        }

        public int MovementCount
        {
            get { return movementCount; }
        }

        public List<string> GetAuditLog()
        {
            return new List<string>(auditLog);
        }

        private void RequireKnown(string sku)
        {
            if (!stock.ContainsKey(sku))
            {
                throw new ArgumentException("unknown sku: " + sku);
            }
        }

        public static void Main(string[] args)
        {
            InventoryLedger ledger = new InventoryLedger();
            ledger.RegisterSku("BOLT-M6", 120, 50);
            ledger.RegisterSku("NUT-M6", 40, 60);
            ledger.Receive("BOLT-M6", 30);
            ledger.Ship("BOLT-M6", 110);
            ledger.Ship("NUT-M6", 5);
            Console.WriteLine(string.Join(", ", ledger.ReorderSuggestions(25)));
            Console.WriteLine(ledger.TurnoverRatio("BOLT-M6", 110));
        }
    }
}
