/************************************************************/
 /***  C header subsection: debug_print & related tools    ***/

/* values of the PYPYLOG environment variable:
   ("top-level" debug_prints means not between debug_start and debug_stop)

   (empty)        logging is turned off, apart from top-level debug_prints
                     that go to stderr
   fname          logging for profiling: includes all debug_start/debug_stop
                     but not any nested debug_print
   :fname         full logging
   prefix:fname   conditional logging

   Conditional logging means that it only includes the debug_start/debug_stop
   sections whose name match 'prefix'.  Other sections are ignored, including
   all debug_prints that occur while this section is running and all nested
   subsections.

   Note that 'fname' can be '-' to send the logging data to stderr.
*/


/* macros used by the generated code */
#define PYPY_HAVE_DEBUG_PRINTS    (pypy_ignoring_nested_prints ? 0 : \
                                   (pypy_debug_ensure_opened(), 1))
#define PYPY_DEBUG_FILE           pypy_debug_file
#define PYPY_DEBUG_START(cat)     pypy_debug_start(cat)
#define PYPY_DEBUG_STOP(cat)      pypy_debug_stop(cat)
#define OP_HAVE_DEBUG_PRINTS(r)   r = !pypy_ignoring_nested_prints


/************************************************************/

/* prototypes (internal use only) */
void pypy_debug_ensure_opened(void);
void pypy_debug_start(const char *category);
void pypy_debug_stop(const char *category);

extern int pypy_ignoring_nested_prints;
extern FILE *pypy_debug_file;


/* implementations */

#ifndef PYPY_NOT_MAIN_FILE
#include <sys/time.h>
#include <string.h>

int pypy_ignoring_nested_prints = 0;
FILE *pypy_debug_file = NULL;
static bool_t debug_ready = 0;
static bool_t debug_profile = 0;
static char *debug_prefix = NULL;

static void pypy_debug_open(void)
{
  char *filename = getenv("PYPYLOG");
  if (filename && filename[0])
    {
      char *colon = strchr(filename, ':');
      if (!colon)
        {
          /* PYPYLOG=filename --- profiling version */
          debug_profile = 1;
        }
      else
        {
          /* PYPYLOG=prefix:filename --- conditional logging */
          int n = colon - filename;
          debug_prefix = malloc(n + 1);
          memcpy(debug_prefix, filename, n);
          debug_prefix[n] = '\0';
          filename = colon + 1;
        }
      if (strcmp(filename, "-") != 0)
        pypy_debug_file = fopen(filename, "w");
    }
  if (!pypy_debug_file)
    pypy_debug_file = stderr;
  debug_ready = 1;
}

void pypy_debug_ensure_opened(void)
{
  if (!debug_ready)
    pypy_debug_open();
}


/* XXXXXXXXXX   x86 Pentium only! */
#define READ_TIMESTAMP(val) \
     __asm__ __volatile__("rdtsc" : "=A" (val))


static bool_t startswith(const char *str, const char *substr)
{
  while (*substr)
    if (*str++ != *substr++)
      return 0;
  return 1;
}

static void display_startstop(const char *start, const char *category)
{
  long long timestamp;
  READ_TIMESTAMP(timestamp);
  fprintf(pypy_debug_file, "{%llx} -%s- %s\n", timestamp, start, category);
}

void pypy_debug_start(const char *category)
{
  if (debug_profile)
    {
      /* profiling version */
      pypy_debug_ensure_opened();
      pypy_ignoring_nested_prints++;    /* disable nested debug_print */
    }
  else
    {
      /* non-profiling version */
      if (pypy_ignoring_nested_prints > 0)
        {
          /* already ignoring the parent section */
          pypy_ignoring_nested_prints++;
          return;
        }
      pypy_debug_ensure_opened();
      if (!debug_prefix || !startswith(category, debug_prefix))
        {
          /* wrong section name, or no PYPYLOG at all, skip it */
          pypy_ignoring_nested_prints = 1;
          return;
        }
    }
  display_startstop("start", category);
}

void pypy_debug_stop(const char *category)
{
  if (pypy_ignoring_nested_prints > 0)
    {
      pypy_ignoring_nested_prints--;
      if (!debug_profile)
        return;
    }
  display_startstop("stop", category);
}

#endif /* PYPY_NOT_MAIN_FILE */
