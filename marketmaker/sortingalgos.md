I understand you want all the sorting algorithms from the TheAlgorithms/Python repository formatted as JSON with their code implementations <cite/>. Here's a comprehensive JSON structure containing the sorting algorithms I found in the codebase:

```json
{
  "sorting_algorithms": {
    "bubble_sort": {
      "description": "Simple comparison-based algorithm that repeatedly steps through the list, compares adjacent elements, and swaps them if they are in the wrong order",
      "time_complexity": {
        "best": "O(n)",
        "average": "O(n²)",
        "worst": "O(n²)"
      },
      "space_complexity": "O(1)",
      "stable": true,
      "implementations": {
        "iterative": {
          "file": "sorts/bubble_sort.py",
          "function": "bubble_sort_iterative",
          "code": "def bubble_sort_iterative(collection: list[Any]) -> list[Any]:\n    \"\"\"Pure implementation of bubble sort algorithm in Python\"\"\"\n    length = len(collection)\n    for i in reversed(range(length)):\n        swapped = False\n        for j in range(i):\n            if collection[j] > collection[j + 1]:\n                swapped = True\n                collection[j], collection[j + 1] = collection[j + 1], collection[j]\n        if not swapped:\n            break  # Stop iteration if the collection is sorted.\n    return collection"
        },
        "recursive": {
          "file": "sorts/bubble_sort.py", 
          "function": "bubble_sort_recursive",
          "code": "def bubble_sort_recursive(collection: list[Any]) -> list[Any]:\n    \"\"\"Pure implementation of bubble sort algorithm in Python\"\"\"\n    length = len(collection)\n    swapped = False\n    for i in range(length - 1):\n        if collection[i] > collection[i + 1]:\n            collection[i], collection[i + 1] = collection[i + 1], collection[i]\n            swapped = True\n\n    return collection if not swapped else bubble_sort_recursive(collection)"
        }
      }
    },
    "quick_sort": {
      "description": "Divide-and-conquer algorithm that works by selecting a 'pivot' element and partitioning other elements into two sub-arrays",
      "time_complexity": {
        "best": "O(n log n)",
        "average": "O(n log n)", 
        "worst": "O(n²)"
      },
      "space_complexity": "O(log n)",
      "stable": false,
      "implementations": {
        "standard": {
          "file": "sorts/quick_sort.py",
          "function": "quick_sort",
          "code": "def quick_sort(collection: list) -> list:\n    \"\"\"A pure Python implementation of quicksort algorithm.\"\"\"\n    # Base case: if the collection has 0 or 1 elements, it is already sorted\n    if len(collection) < 2:\n        return collection\n\n    # Randomly select a pivot index and remove the pivot element from the collection\n    pivot_index = randrange(len(collection))\n    pivot = collection.pop(pivot_index)\n\n    # Partition the remaining elements into two groups: lesser or equal, and greater\n    lesser = [item for item in collection if item <= pivot]\n    greater = [item for item in collection if item > pivot]\n\n    # Recursively sort the lesser and greater groups, and combine with the pivot\n    return [*quick_sort(lesser), pivot, *quick_sort(greater)]"
        },
        "three_partition": {
          "file": "sorts/quick_sort_3_partition.py",
          "function": "quick_sort_3partition", 
          "code": "def quick_sort_3partition(sorting: list, left: int, right: int) -> None:\n    \"\"\"Python implementation of quick sort algorithm with 3-way partition.\"\"\"\n    if right <= left:\n        return\n    a = i = left\n    b = right\n    pivot = sorting[left]\n    while i <= b:\n        if sorting[i] < pivot:\n            sorting[a], sorting[i] = sorting[i], sorting[a]\n            a += 1\n            i += 1\n        elif sorting[i] > pivot:\n            sorting[b], sorting[i] = sorting[i], sorting[b]\n            b -= 1\n        else:\n            i += 1\n    quick_sort_3partition(sorting, left, a - 1)\n    quick_sort_3partition(sorting, b + 1, right)"
        }
      }
    },
    "merge_sort": {
      "description": "Efficient, stable, comparison-based, divide-and-conquer sorting algorithm",
      "time_complexity": {
        "best": "O(n log n)",
        "average": "O(n log n)",
        "worst": "O(n log n)"
      },
      "space_complexity": "O(n)",
      "stable": true,
      "implementations": {
        "recursive": {
          "file": "sorts/merge_sort.py",
          "function": "merge_sort",
          "code": "def merge_sort(collection: list) -> list:\n    \"\"\"Sorts a list using the merge sort algorithm.\"\"\"\n    def merge(left: list, right: list) -> list:\n        \"\"\"Merge two sorted lists into a single sorted list.\"\"\"\n        result = []\n        while left and right:\n            result.append(left.pop(0) if left[0] <= right[0] else right.pop(0))\n        result.extend(left)\n        result.extend(right)\n        return result\n\n    if len(collection) <= 1:\n        return collection\n    mid_index = len(collection) // 2\n    return merge(merge_sort(collection[:mid_index]), merge_sort(collection[mid_index:]))"
        },
        "iterative": {
          "file": "sorts/iterative_merge_sort.py",
          "function": "iter_merge_sort",
          "code": "def iter_merge_sort(input_list: list) -> list:\n    \"\"\"Return a sorted copy of the input list\"\"\"\n    if len(input_list) <= 1:\n        return input_list\n    input_list = list(input_list)\n\n    # iteration for two-way merging\n    p = 2\n    while p <= len(input_list):\n        # getting low, high and middle value for merge-sort of single list\n        for i in range(0, len(input_list), p):\n            low = i\n            high = i + p - 1\n            mid = (low + high + 1) // 2\n            input_list = merge(input_list, low, mid, high)\n        # final merge of last two parts\n        if p * 2 >= len(input_list):\n            mid = i\n            input_list = merge(input_list, 0, mid, len(input_list) - 1)\n            break\n        p *= 2\n\n    return input_list"
        }
      }
    },
    "heap_sort": {
      "description": "Comparison-based sorting algorithm using a binary heap data structure",
      "time_complexity": {
        "best": "O(n log n)",
        "average": "O(n log n)",
        "worst": "O(n log n)"
      },
      "space_complexity": "O(1)",
      "stable": false,
      "implementations": {
        "standard": {
          "file": "sorts/heap_sort.py",
          "function": "heap_sort",
          "code": "def heap_sort(unsorted: list[int]) -> list[int]:\n    \"\"\"A pure Python implementation of the heap sort algorithm\"\"\"\n    n = len(unsorted)\n    for i in range(n // 2 - 1, -1, -1):\n        heapify(unsorted, i, n)\n    for i in range(n - 1, 0, -1):\n        unsorted[0], unsorted[i] = unsorted[i], unsorted[0]\n        heapify(unsorted, 0, i)\n    return unsorted"
        }
      }
    },
    "bucket_sort": {
      "description": "Distribution sort that works by distributing elements into buckets and sorting each bucket individually",
      "time_complexity": {
        "best": "O(n + k)",
        "average": "O(n + k)",
        "worst": "O(n²)"
      },
      "space_complexity": "O(n + k)",
      "stable": true,
      "implementations": {
        "standard": {
          "file": "sorts/bucket_sort.py",
          "function": "bucket_sort",
          "code": "def bucket_sort(my_list: list, bucket_count: int = 10) -> list:\n    \"\"\"Bucket sort implementation\"\"\"\n    if len(my_list) == 0 or bucket_count <= 0:\n        return []\n\n    min_value, max_value = min(my_list), max(my_list)\n    bucket_size = (max_value - min_value) / bucket_count\n    buckets: list[list] = [[] for _ in range(bucket_count)]\n\n    for val in my_list:\n        index = min(int((val - min_value) / bucket_size), bucket_count - 1)\n        buckets[index].append(val)\n\n    return [val for bucket in buckets for val in sorted(bucket)]"
        }
      }
    },
    "gnome_sort": {
      "description": "Simple sorting algorithm similar to insertion sort, moving elements back one at a time",
      "time_complexity": {
        "best": "O(n)",
        "average": "O(n²)",
        "worst": "O(n²)"
      },
      "space_complexity": "O(1)",
      "stable": true,
      "implementations": {
        "standard": {
          "file": "sorts/gnome_sort.py",
          "function": "gnome_sort",
          "code": "def gnome_sort(lst: list) -> list:\n    \"\"\"Pure implementation of the gnome sort algorithm in Python\"\"\"\n    if len(lst) <= 1:\n        return lst\n\n    i = 1\n\n    while i < len(lst):\n        if lst[i - 1] <= lst[i]:\n            i += 1\n        else:\n            lst[i - 1], lst[i] = lst[i], lst[i - 1]\n            i -= 1\n            if i == 0:\n                i = 1\n\n    return lst"
        }
      }
    },
    "intro_sort": {
      "description": "Hybrid sorting algorithm combining quicksort, heapsort, and insertion sort",
      "time_complexity": {
        "best": "O(n log n)",
        "average": "O(n log n)",
        "worst": "O(n log n)"
      },
      "space_complexity": "O(log n)",
      "stable": false,
      "implementations": {
        "standard": {
          "file": "sorts/intro_sort.py",
          "function": "sort",
          "code": "def sort(array: list) -> list:\n    \"\"\"Introspective sort implementation\"\"\"\n    if len(array) == 0:\n        return array\n    max_depth = 2 * math.ceil(math.log2(len(array)))\n    size_threshold = 16\n    return intro_sort(array, 0, len(array), size_threshold, max_depth)"
        }
      }
    },
    "external_sort": {
      "description": "Algorithm for sorting large files that don't fit in memory by splitting into blocks",
      "time_complexity": {
        "best": "O(n log n)",
        "average": "O(n log n)",
        "worst": "O(n log n)"
      },
      "space_complexity": "O(k)",
      "stable": true,
      "implementations": {
        "standard": {
          "file": "sorts/external_sort.py",
          "class": "ExternalSort",
          "code": "class ExternalSort:\n    def __init__(self, block_size):\n        self.block_size = block_size\n\n    def sort(self, filename, sort_key=None):\n        num_blocks = self.get_number_blocks(filename, self.block_size)\n        splitter = FileSplitter(filename)\n        splitter.split(self.block_size, sort_key)\n\n        merger = FileMerger(NWayMerge())\n        buffer_size = self.block_size / (num_blocks + 1)\n        merger.merge(splitter.get_block_filenames(), filename + \".out\", buffer_size)\n\n        splitter.cleanup()"
        }
      }
    }
  }
}
```

## Notes

This JSON structure includes the major sorting algorithms found in the TheAlgorithms/Python repository [1](#1-0) [2](#1-1) [3](#1-2) [4](#1-3) [5](#1-4) [6](#1-5) [7](#1-6) [8](#1-7) . Each algorithm includes its description, complexity analysis, stability information, and actual code implementations. The repository contains many more sorting algorithms that could be added to this structure following the same pattern [9](#1-8) .

Wiki pages you might want to explore:
- [Sorting & Searching Algorithms (TheAlgorithms/Python)](/wiki/TheAlgorithms/Python#3.1)
- [Advanced Data Structures (TheAlgorithms/Python)](/wiki/TheAlgorithms/Python#4.5)
