/*
 * CleanRoom_MergeSort_B.java
 * "Clean room" Merge Sort — same algorithm, completely different expression.
 * All identifiers, comments, whitespace, and style differ from version A.
 * AST structure should be equivalent; raw_winnowing should be very low.
 */
class CleanRoom_MergeSort_B {

    // Recursively divide and conquer the input sequence
    static void sortRecursive(int[] data) {
        if (data == null || data.length < 2) {
            return;
        }
        int half = data.length / 2;
        int[] lo = new int[half];
        int[] hi = new int[data.length - half];

        System.arraycopy(data, 0, lo, 0, half);
        System.arraycopy(data, half, hi, 0, data.length - half);

        sortRecursive(lo);
        sortRecursive(hi);
        combine(data, lo, hi);
    }

    // Interleave two ordered sequences into a single ordered output
    private static void combine(int[] out, int[] seq1, int[] seq2) {
        int p = 0, q = 0, r = 0;

        while (p < seq1.length && q < seq2.length) {
            if (seq1[p] <= seq2[q]) {
                out[r++] = seq1[p++];
            } else {
                out[r++] = seq2[q++];
            }
        }

        while (p < seq1.length) {
            out[r++] = seq1[p++];
        }
        while (q < seq2.length) {
            out[r++] = seq2[q++];
        }
    }
}
