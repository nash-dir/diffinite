package com.acme.warehouse

/**
 * Tracks stock levels per SKU and emits reorder suggestions.
 */
class InventoryLedger {

    private val stock = HashMap<String, Int>()
    private val reorderPoint = HashMap<String, Int>()
    private val auditLog = ArrayList<String>()
    var movementCount = 0
        private set

    fun registerSku(sku: String?, initialQty: Int, reorderAt: Int) {
        require(!sku.isNullOrEmpty()) { "sku must not be empty" }
        require(initialQty >= 0 && reorderAt >= 0) { "quantities must be non-negative" }
        stock[sku!!] = initialQty
        reorderPoint[sku] = reorderAt
        auditLog.add("REGISTER $sku qty=$initialQty")
    }

    fun receive(sku: String, qty: Int): Int {
        requireKnown(sku)
        require(qty > 0) { "receive qty must be positive" }
        val updated = stock.getValue(sku) + qty
        stock[sku] = updated
        movementCount++
        auditLog.add("RECEIVE $sku +$qty -> $updated")
        return updated
    }

    fun ship(sku: String, qty: Int): Int {
        requireKnown(sku)
        val current = stock.getValue(sku)
        if (qty > current) {
            auditLog.add("SHORT $sku wanted=$qty have=$current")
            throw IllegalStateException("insufficient stock for $sku")
        }
        val updated = current - qty
        stock[sku] = updated
        movementCount++
        auditLog.add("SHIP $sku -$qty -> $updated")
        return updated
    }

    fun reorderSuggestions(batchSize: Int): List<String> =
        stock.entries
            .filter { (sku, qty) -> qty <= reorderPoint.getValue(sku) }
            .map { (sku, qty) ->
                val deficit = reorderPoint.getValue(sku) - qty
                val batches = deficit / batchSize + 1
                "$sku:${batches * batchSize}"
            }
            .sorted()

    fun turnoverRatio(sku: String, periodShipped: Int): Double {
        requireKnown(sku)
        val onHand = stock.getValue(sku)
        return if (onHand == 0) Double.POSITIVE_INFINITY else periodShipped.toDouble() / onHand
    }

    fun getAuditLog(): List<String> = auditLog.toList()

    private fun requireKnown(sku: String) {
        require(stock.containsKey(sku)) { "unknown sku: $sku" }
    }
}

fun main() {
    val ledger = InventoryLedger()
    ledger.registerSku("BOLT-M6", 120, 50)
    ledger.registerSku("NUT-M6", 40, 60)
    ledger.receive("BOLT-M6", 30)
    ledger.ship("BOLT-M6", 110)
    ledger.ship("NUT-M6", 5)
    println(ledger.reorderSuggestions(25))
    println(ledger.turnoverRatio("BOLT-M6", 110))
}
