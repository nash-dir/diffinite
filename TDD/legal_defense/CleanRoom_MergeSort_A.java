/**
 * CleanRoom_MergeSort_A.java
 * Standard Merge Sort implementation — "original" version.
 * Uses conventional variable naming, Javadoc comments.
 */
public class CleanRoom_MergeSort_A {

    /**
     * Sorts the given array using the Merge Sort algorithm.
     * @param array the array to sort
     */
    public static void mergeSort(int[] array) {
        if (array == null || array.length <= 1) {
            return;
        }
        int midPoint = array.length / 2;
        int[] leftHalf = new int[midPoint];
        int[] rightHalf = new int[array.length - midPoint];

        // Copy elements to left sub-array
        for (int i = 0; i < midPoint; i++) {
            leftHalf[i] = array[i];
        }
        // Copy elements to right sub-array
        for (int i = midPoint; i < array.length; i++) {
            rightHalf[i - midPoint] = array[i];
        }

        mergeSort(leftHalf);
        mergeSort(rightHalf);
        merge(array, leftHalf, rightHalf);
    }

    /**
     * Merges two sorted sub-arrays into one sorted array.
     */
    private static void merge(int[] result, int[] left, int[] right) {
        int leftIndex = 0;
        int rightIndex = 0;
        int resultIndex = 0;

        while (leftIndex < left.length && rightIndex < right.length) {
            if (left[leftIndex] <= right[rightIndex]) {
                result[resultIndex++] = left[leftIndex++];
            } else {
                result[resultIndex++] = right[rightIndex++];
            }
        }

        while (leftIndex < left.length) {
            result[resultIndex++] = left[leftIndex++];
        }
        while (rightIndex < right.length) {
            result[resultIndex++] = right[rightIndex++];
        }
    }
}
