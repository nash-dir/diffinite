#include <stdio.h>
#include <stdlib.h>

/* Binary search and insertion sort, student A. */

int binary_search(const int *arr, int n, int target)
{
    int lo = 0, hi = n - 1;
    while (lo <= hi) {
        int mid = lo + (hi - lo) / 2;
        if (arr[mid] == target)
            return mid;
        if (arr[mid] < target)
            lo = mid + 1;
        else
            hi = mid - 1;
    }
    return -1;
}

void insertion_sort(int *arr, int n)
{
    for (int i = 1; i < n; i++) {
        int key = arr[i];
        int j = i - 1;
        while (j >= 0 && arr[j] > key) {
            arr[j + 1] = arr[j];
            j--;
        }
        arr[j + 1] = key;
    }
}

static void swap(int *a, int *b)
{
    int t = *a;
    *a = *b;
    *b = t;
}

void bubble_sort(int *arr, int n)
{
    for (int i = 0; i < n - 1; i++) {
        int swapped = 0;
        for (int j = 0; j < n - 1 - i; j++) {
            if (arr[j] > arr[j + 1]) {
                swap(&arr[j], &arr[j + 1]);
                swapped = 1;
            }
        }
        if (!swapped)
            break;
    }
}

int main(void)
{
    int data[] = {9, 4, 7, 1, 8, 2};
    int n = sizeof(data) / sizeof(data[0]);
    insertion_sort(data, n);
    for (int i = 0; i < n; i++)
        printf("%d ", data[i]);
    printf("\nindex of 7: %d\n", binary_search(data, n, 7));
    return 0;
}
